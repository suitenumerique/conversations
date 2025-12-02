import {
  Message,
  ReasoningUIPart,
  SourceUIPart,
  ToolInvocationUIPart,
} from '@ai-sdk/ui-utils';
import { Modal, ModalSize } from '@openfun/cunningham-react';
import 'katex/dist/katex.min.css'; // `rehype-katex` does not import the CSS for you
import { useRouter } from 'next/router';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { MarkdownHooks } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import rehypePrettyCode from 'rehype-pretty-code';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { Box, Icon, Loader, Text } from '@/components';
import { useUploadFile } from '@/features/attachments/hooks/useUploadFile';
import { useChat } from '@/features/chat/api/useChat';
import { getConversation } from '@/features/chat/api/useConversation';
import { useCreateChatConversation } from '@/features/chat/api/useCreateConversation';
import {
  LLMModel,
  useLLMConfiguration,
} from '@/features/chat/api/useLLMConfiguration';
import { AttachmentList } from '@/features/chat/components/AttachmentList';
import { ChatError } from '@/features/chat/components/ChatError';
import { CodeBlock } from '@/features/chat/components/CodeBlock';
import { FeedbackButtons } from '@/features/chat/components/FeedbackButtons';
import { InputChat } from '@/features/chat/components/InputChat';
import { SourceItemList } from '@/features/chat/components/SourceItemList';
import { ToolInvocationItem } from '@/features/chat/components/ToolInvocationItem';
import { useClipboard } from '@/hook';
import { useResponsiveStore } from '@/stores';

import { useSourceMetadataCache } from '../hooks';
import { useChatPreferencesStore } from '../stores/useChatPreferencesStore';
import { usePendingChatStore } from '../stores/usePendingChatStore';
import { useScrollStore } from '../stores/useScrollStore';

// Define Attachment type locally (mirroring backend structure)
export interface Attachment {
  name?: string;
  contentType?: string;
  url: string;
}

export const Chat = ({
  initialConversationId = undefined,
}: {
  initialConversationId: string | undefined;
}) => {
  const { t } = useTranslation();
  const copyToClipboard = useClipboard();
  const { isMobile } = useResponsiveStore();

  const streamProtocol = 'data'; // or 'text'

  const {
    forceWebSearch,
    toggleForceWebSearch,
    selectedModelHrid,
    setSelectedModelHrid,
  } = useChatPreferencesStore();

  const { data: llmConfig } = useLLMConfiguration();
  const [selectedModel, setSelectedModel] = useState<LLMModel | null>(null);

  const [conversationId, setConversationId] = useState(initialConversationId);
  const apiUrl = conversationId
    ? `chats/${conversationId}/conversation/?protocol=${streamProtocol}`
    : `chats/conversation/?protocol=${streamProtocol}`;

  // Initialize upload hook
  const { uploadFile, isErrorAttachment, errorAttachment } = useUploadFile(
    conversationId || '',
  );

  useEffect(() => {
    (window as { globalForceWebSearch?: boolean }).globalForceWebSearch =
      forceWebSearch;
  }, [forceWebSearch]);

  // Update selected model when LLM config loads
  useEffect(() => {
    if (llmConfig?.models && !selectedModel) {
      let modelToSelect: LLMModel | undefined;

      if (selectedModelHrid) {
        // Try to find the previously selected model
        modelToSelect = llmConfig.models.find(
          (model) =>
            model.hrid === selectedModelHrid && model.is_active !== false,
        );
      }

      // If no saved model or saved model not found/inactive, use default
      if (!modelToSelect) {
        modelToSelect = llmConfig.models.find((model) => model.is_default);
      }

      if (modelToSelect) {
        setSelectedModel(modelToSelect);
      }
    }
  }, [llmConfig, selectedModel, selectedModelHrid]);

  // Update store when model selection changes
  useEffect(() => {
    if (selectedModel?.hrid !== selectedModelHrid) {
      setSelectedModelHrid(selectedModel?.hrid || null);
    }
  }, [selectedModel, selectedModelHrid, setSelectedModelHrid]);

  const handleModelSelect = (model: LLMModel) => {
    setSelectedModel(model);
  };

  const router = useRouter();
  const [files, setFiles] = useState<FileList | null>(null);
  const [isUploadingFiles, setIsUploadingFiles] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [chatErrorModal, setChatErrorModal] = useState<{
    title: string;
    message: string;
  } | null>(null);

  const { setIsAtTop } = useScrollStore();

  // Gérer le scroll pour mettre à jour l'état du header
  useEffect(() => {
    const handleScroll = () => {
      if (chatContainerRef.current) {
        const scrollTop = chatContainerRef.current.scrollTop;
        setIsAtTop(scrollTop <= 5);
      }
    };

    const container = chatContainerRef.current;
    if (container) {
      container.addEventListener('scroll', handleScroll, { passive: true });
      handleScroll(); // Vérifier la position initiale

      return () => container.removeEventListener('scroll', handleScroll);
    }
  }, [setIsAtTop]);

  const [isSourceOpen, setIsSourceOpen] = useState<string | null>(null);
  const { prefetchMetadata, getMetadata } = useSourceMetadataCache();

  const [initialConversationMessages, setInitialConversationMessages] =
    useState<Message[] | undefined>(undefined);
  const [pendingFirstMessage, setPendingFirstMessage] = useState<{
    event: FormEvent<HTMLFormElement>;
    attachments?: Attachment[];
    forceWebSearch?: boolean;
  } | null>(null);
  const [shouldAutoSubmit, setShouldAutoSubmit] = useState(false);
  const [shouldRetry, setShouldRetry] = useState(false);
  const retryOriginalInputRef = useRef<string>('');
  const retryOriginalFilesRef = useRef<FileList | null>(null);
  const [hasInitialized, setHasInitialized] = useState(false);
  const [streamingMessageHeight, setStreamingMessageHeight] = useState<
    number | null
  >(null);
  const lastUserMessageIdRef = useRef<string | null>(null);
  const hasScrolledToBottomOnLoadRef = useRef(false);
  const lastSubmissionRef = useRef<{
    input: string;
    files: FileList | null;
    event: FormEvent<HTMLFormElement>;
    options?: Record<string, unknown>;
  } | null>(null);

  const { mutate: createChatConversation } = useCreateChatConversation();

  // Zustand store for pending chat state
  const {
    input: pendingInput,
    files: pendingFiles,
    setPendingChat,
    clearPendingChat,
  } = usePendingChatStore();

  const scrollToBottom = useCallback(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: hasInitialized ? 'smooth' : 'auto',
      });
    }
  }, [hasInitialized]);

  // Show error modal for upload errors
  useEffect(() => {
    if (isErrorAttachment && errorAttachment) {
      setChatErrorModal({
        title: t('Upload Error'),
        message: t('Failed to upload file'),
      });
    }
  }, [isErrorAttachment, errorAttachment, t]);

  // Handle errors from the chat API
  const onErrorChat = (error: Error) => {
    if (error.message === 'attachment_summary_not_supported') {
      setChatErrorModal({
        title: t('Attachment summary not supported'),
        message: t('The summary feature is not supported yet.'),
      });
    }
    console.error('Chat error:', error);
  };

  const {
    messages,
    input,
    handleSubmit: baseHandleSubmit,
    handleInputChange,
    status,
    stop: stopChat,
    setMessages,
  } = useChat({
    id: conversationId,
    initialMessages: initialConversationMessages,
    api: apiUrl,
    streamProtocol: streamProtocol,
    sendExtraMessageFields: true,
    onError: onErrorChat,
  });

  const stopGeneration = async () => {
    stopChat();

    const response = await fetchAPI(`chats/${conversationId}/stop-streaming/`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new APIError(
        'Failed to stop the conversation',
        await errorCauses(response),
      );
    }
  };

  const toggleWebSearch = () => {
    toggleForceWebSearch();
  };

  const handleStop = () => {
    void stopGeneration();
  };

  const handleSubmitWrapper = (event: FormEvent<HTMLFormElement>) => {
    void handleSubmit(event);
  };

  const handleRetry = () => {
    if (!lastSubmissionRef.current || !setMessages) {
      return;
    }

    const { input: lastInput, files: lastFiles } = lastSubmissionRef.current;

    const lastAssistantIndex = messages.findLastIndex(
      (msg) => msg.role === 'assistant',
    );
    if (lastAssistantIndex !== -1) {
      setMessages(messages.filter((_, index) => index !== lastAssistantIndex));
    }

    retryOriginalInputRef.current = input;
    retryOriginalFilesRef.current = files;
    handleInputChange({
      target: { value: lastInput },
    } as ChangeEvent<HTMLTextAreaElement>);
    setFiles(lastFiles);
    setShouldRetry(true);
  };

  // Précharger les métadonnées des sources dès que les messages arrivent
  useEffect(() => {
    messages.forEach((message) => {
      if (message.parts) {
        const sourceParts = message.parts.filter(
          (part): part is SourceUIPart => part.type === 'source',
        );
        sourceParts.forEach((part) => {
          void prefetchMetadata(part.source.url);
        });
      }
    });
  }, [messages, prefetchMetadata]);

  const openSources = (messageId: string) => {
    if (isSourceOpen === messageId) {
      setIsSourceOpen(null);
      return;
    }
    const message = messages.find((msg) => msg.id === messageId);
    if (message?.parts) {
      const sourceParts = message.parts.filter(
        (part): part is SourceUIPart => part.type === 'source',
      );
      if (sourceParts.length > 0) {
        setIsSourceOpen(messageId);
      }
    }
  };

  // Calculer la hauteur pour le message de streaming
  const calculateStreamingHeight = useCallback(() => {
    if (messages.length <= 2) {
      return;
    }

    if (chatContainerRef.current) {
      const container = chatContainerRef.current;
      const containerHeight = container.clientHeight;

      const userMessages = messages.filter((msg) => msg.role === 'user');
      const lastUserMessage = userMessages[userMessages.length - 1];

      if (lastUserMessage) {
        const messageElements = container.querySelectorAll('[data-message-id]');
        const lastUserMessageElement = Array.from(messageElements).find(
          (el) => el.getAttribute('data-message-id') === lastUserMessage.id,
        );

        if (lastUserMessageElement) {
          const userMessageHeight = (lastUserMessageElement as HTMLElement)
            .offsetHeight;

          const availableHeight = containerHeight - userMessageHeight - 38;

          if (streamingMessageHeight !== availableHeight) {
            setStreamingMessageHeight(availableHeight);
          }
        }
      }
    }
  }, [messages, streamingMessageHeight]);

  // Détecter l'arrivée d'un nouveau message user et retirer la hauteur de l'ancien
  useEffect(() => {
    const userMessages = messages.filter((msg) => msg.role === 'user');
    const lastUserMessage = userMessages[userMessages.length - 1];

    if (
      lastUserMessage &&
      lastUserMessage.id !== lastUserMessageIdRef.current
    ) {
      if (lastUserMessageIdRef.current !== null) {
        setStreamingMessageHeight(null);
      }
      lastUserMessageIdRef.current = lastUserMessage.id;
    }
  }, [messages]);

  // Calculer la hauteur pendant submitted/streaming
  useEffect(() => {
    if (status === 'submitted' || status === 'streaming') {
      calculateStreamingHeight();
    }
  }, [status, calculateStreamingHeight]);

  // Scroller vers la question au moment du submit
  useEffect(() => {
    if (status !== 'submitted' || !chatContainerRef.current) {
      return;
    }

    const lastUserMessage = messages.filter((msg) => msg.role === 'user').pop();
    if (!lastUserMessage) {
      return;
    }

    requestAnimationFrame(() => {
      const messageElement = chatContainerRef.current?.querySelector(
        `[data-message-id="${lastUserMessage.id}"]`,
      );

      messageElement?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });
  }, [status, messages]);

  // Synchronize conversationId state with prop when it changes (e.g., after navigation)
  useEffect(() => {
    setConversationId(initialConversationId);
    // Reset input when conversation changes
    if (initialConversationId !== conversationId) {
      handleInputChange({
        target: { value: '' },
      } as ChangeEvent<HTMLTextAreaElement>);
      setHasInitialized(false); // Réinitialiser pour permettre le scroll au prochain chargement
    }
  }, [initialConversationId, conversationId, handleInputChange]);

  // On mount, if there is pending input/files, initialize state and set flag
  useEffect(() => {
    if (
      (pendingInput && pendingInput.trim()) ||
      (pendingFiles && pendingFiles.length > 0)
    ) {
      if (pendingInput) {
        const syntheticEvent = {
          target: { value: pendingInput },
        } as ChangeEvent<HTMLInputElement>;
        handleInputChange(syntheticEvent);
      }
      if (pendingFiles) {
        setFiles(pendingFiles);
      }
      setShouldAutoSubmit(true);
      clearPendingChat();
    } else {
      clearPendingChat();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When shouldAutoSubmit is set, and input/files are ready, submit
  useEffect(() => {
    if (shouldAutoSubmit && (input.trim() || (files && files.length > 0))) {
      // Create a synthetic event for form submission
      const form = document.createElement('form');
      const syntheticFormEvent = {
        preventDefault: () => {},
        target: form,
      } as unknown as FormEvent<HTMLFormElement>;
      void handleSubmit(syntheticFormEvent);
      setShouldAutoSubmit(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAutoSubmit, input, files]);

  useEffect(() => {
    if (
      shouldRetry &&
      lastSubmissionRef.current &&
      input === lastSubmissionRef.current.input
    ) {
      const { event } = lastSubmissionRef.current;

      void handleSubmit(event);
      handleInputChange({
        target: { value: retryOriginalInputRef.current },
      } as ChangeEvent<HTMLTextAreaElement>);
      setFiles(retryOriginalFilesRef.current);

      setShouldRetry(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldRetry, input, files]);

  // Fetch initial conversation messages if initialConversationId is provided and no pending input
  useEffect(() => {
    hasScrolledToBottomOnLoadRef.current = false; // Réinitialiser au début du chargement
    let ignore = false;
    async function fetchInitialMessages() {
      if (initialConversationId && !pendingInput) {
        try {
          const conversation = await getConversation({
            id: initialConversationId,
          });
          if (!ignore) {
            setInitialConversationMessages(conversation.messages);
            setHasInitialized(true);
          }
        } catch {
          // Optionally handle error (e.g., setInitialConversationMessages([]) or show error)
          if (!ignore) {
            setInitialConversationMessages([]);
            setHasInitialized(true);
          }
        }
      }
    }
    void fetchInitialMessages();
    return () => {
      ignore = true;
    };
    // Only run when initialConversationId or pendingInput changes
  }, [initialConversationId, pendingInput]);

  useEffect(() => {
    if (
      hasInitialized &&
      conversationId &&
      messages.length > 0 &&
      !hasScrolledToBottomOnLoadRef.current
    ) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (chatContainerRef.current) {
            chatContainerRef.current.scrollTo({
              top: chatContainerRef.current.scrollHeight,
              behavior: 'auto',
            });
          }
          hasScrolledToBottomOnLoadRef.current = true;
        });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasInitialized, messages.length]);

  // Custom handleSubmit to include attachments and handle chat creation
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    // Upload files to server and get URLs
    let attachments: Attachment[] = [];
    if (files && files.length > 0 && conversationId) {
      try {
        setIsUploadingFiles(true);
        const uploadPromises = Array.from(files).map(async (file) => {
          const url = await uploadFile(file);

          return {
            name: file.name,
            contentType: file.type,
            url: url,
          };
        });
        attachments = await Promise.all(uploadPromises);
        setIsUploadingFiles(false);
      } catch (error) {
        setIsUploadingFiles(false);
        console.error('File upload error:', error);
        setChatErrorModal({
          title: t('Upload Error'),
          message: t('Failed to upload files. Please try again.'),
        });
        return;
      }
    }

    if (!conversationId) {
      // Save the event and files, then create the chat
      setPendingFirstMessage({ event, attachments, forceWebSearch });
      // Save input and files to Zustand store before navigation
      setPendingChat(input, files);
      void createChatConversation(
        { title: input.length > 100 ? `${input.slice(0, 97)}...` : input },
        {
          onSuccess: (data) => {
            setConversationId(data.id);
            // Update the URL to /chat/[id]/
            void router.push(`/chat/${data.id}/`);
            // After setting the conversationId, submit the pending message
            setTimeout(() => {
              if (pendingFirstMessage) {
                // Prepare options with attachments
                const options: Record<string, unknown> = {};
                if (
                  pendingFirstMessage.attachments &&
                  pendingFirstMessage.attachments.length > 0
                ) {
                  options.experimental_attachments =
                    pendingFirstMessage.attachments;
                }

                if (Object.keys(options).length > 0) {
                  baseHandleSubmit(pendingFirstMessage.event, options);
                } else {
                  baseHandleSubmit(pendingFirstMessage.event);
                }
                setFiles(null);
                if (fileInputRef.current) {
                  fileInputRef.current.value = '';
                }
                setPendingFirstMessage(null);
              }
            }, 0);
          },
        },
      );
      return;
    }

    // Prepare options with attachments
    const options: Record<string, unknown> = {};
    if (attachments.length > 0) {
      options.experimental_attachments = attachments;
    }

    lastSubmissionRef.current = {
      input,
      files,
      event,
      options: Object.keys(options).length > 0 ? options : undefined,
    };

    if (Object.keys(options).length > 0) {
      baseHandleSubmit(event, options);
    } else {
      baseHandleSubmit(event);
    }
    // Attendre un peu avant de vider les fichiers pour s'assurer qu'ils sont traités
    setTimeout(() => {
      setFiles(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }, 100);
  };

  return (
    <Box
      $direction="column"
      $width="100%"
      $css={`
          flex-basis: auto;
          height: 100%;
          flex-grow: 1;
        `}
    >
      <Box
        ref={chatContainerRef}
        $gap="1rem"
        $padding={{ all: 'base', left: '13px', bottom: '0', right: '0' }}
        $width="100%"
        $flex={1}
        $overflow="auto"
        $css={`
          flex-basis: auto;
          flex-grow: 1;
          position: relative;
          margin-bottom: 0;
          padding-bottom: 20px;
          height: ${messages.length > 0 ? 'calc(100vh - 62px)' : '0'}; 
          max-height: ${messages.length > 0 ? 'calc(100vh - 62px)' : '0'};
        `}
      >
        {messages.length > 0 && (
          <Box>
            {messages.map((message, index) => {
              const isLastMessage = index === messages.length - 1;
              const isLastAssistantMessageInConversation =
                message.role === 'assistant' &&
                index ===
                  messages.findLastIndex((msg) => msg.role === 'assistant');
              const isFirstConversationMessage = messages.length <= 2;
              const shouldApplyStreamingHeight =
                isLastAssistantMessageInConversation &&
                isLastMessage &&
                streamingMessageHeight &&
                !isFirstConversationMessage;
              const isCurrentlyStreaming =
                isLastAssistantMessageInConversation &&
                (status === 'streaming' || status === 'submitted');

              return (
                <Box
                  key={message.id}
                  data-message-id={message.id}
                  $css={`
                    display: flex;
                    width: 100%;
                    margin: auto;
                    margin-bottom: ${isLastAssistantMessageInConversation ? '30px' : '0px'};
                    color: var(--c--theme--colors--greyscale-850);
                    padding-left: 12px;
                    padding-right: 12px;
                    max-width: 750px;
                    text-align: left;
                    overflow-wrap: anywhere;
                    flex-direction: ${message.role === 'user' ? 'row-reverse' : 'row'};
                  `}
                >
                  <Box
                    $display="block"
                    $width={`${message.role === 'user' ? 'auto' : '100%'}`}
                  >
                    {message.experimental_attachments &&
                      message.experimental_attachments.length > 0 && (
                        <Box>
                          <AttachmentList
                            attachments={message.experimental_attachments}
                            isReadOnly={true}
                          />
                        </Box>
                      )}
                    <Box
                      $radius="8px"
                      $width={`${message.role === 'user' ? 'auto' : '100%'}`}
                      $maxWidth="100%"
                      $padding={`${message.role === 'user' ? '12px' : '0'}`}
                      $margin={{ vertical: 'base' }}
                      $background={`${message.role === 'user' ? '#EEF1F4' : 'white'}`}
                      $css={`
                      display: inline-block;
                      float: right;
                      ${shouldApplyStreamingHeight ? `min-height: ${streamingMessageHeight}px;` : ''}`}
                    >
                      {/* Message content */}
                      {message.content && (
                        <Box
                          className="mainContent-chat"
                          $padding={{ all: 'xxs' }}
                        >
                          <p className="sr-only">
                            {message.role === 'user'
                              ? t('You said: ')
                              : t('Assistant IA replied: ')}
                          </p>
                          <MarkdownHooks
                            remarkPlugins={[remarkGfm, remarkMath]}
                            rehypePlugins={[
                              [
                                rehypePrettyCode,
                                {
                                  theme: 'github-dark-dimmed',
                                },
                              ],
                              rehypeKatex,
                            ]}
                            components={{
                              // Custom components for Markdown rendering
                              // eslint-disable-next-line @typescript-eslint/no-unused-vars
                              p: ({ node, ...props }) => (
                                <Text
                                  as="p"
                                  $css="display: block"
                                  $theme="greyscale"
                                  $variation="850"
                                  {...props}
                                />
                              ),
                              a: ({ children, ...props }) => (
                                <a target="_blank" {...props}>
                                  {children}
                                </a>
                              ),
                              // eslint-disable-next-line @typescript-eslint/no-unused-vars
                              pre: ({ node, children, ...props }) => (
                                <CodeBlock {...props}>{children}</CodeBlock>
                              ),
                            }}
                          >
                            {message.content}
                          </MarkdownHooks>
                        </Box>
                      )}

                      <Box $direction="column" $gap="2">
                        {isCurrentlyStreaming &&
                          isLastAssistantMessageInConversation &&
                          status === 'streaming' &&
                          message.parts?.some(
                            (part) =>
                              part.type === 'tool-invocation' &&
                              part.toolInvocation.toolName !==
                                'document_parsing',
                          ) && (
                            <Box
                              $direction="row"
                              $align="center"
                              $gap="6px"
                              $width="100%"
                              $maxWidth="750px"
                              $margin={{
                                all: 'auto',
                                top: 'base',
                                bottom: 'md',
                              }}
                            >
                              <Loader />
                              <Text $variation="600" $size="md">
                                {(() => {
                                  const toolInvocation = message.parts?.find(
                                    (part) =>
                                      part.type === 'tool-invocation' &&
                                      part.toolInvocation.toolName !==
                                        'document_parsing',
                                  );
                                  if (
                                    toolInvocation?.type ===
                                      'tool-invocation' &&
                                    toolInvocation.toolInvocation.toolName ===
                                      'summarize'
                                  ) {
                                    return t('Summarizing...');
                                  }
                                  return t('Search...');
                                })()}
                              </Text>
                            </Box>
                          )}
                        {message.parts
                          ?.filter(
                            (part) =>
                              part.type === 'reasoning' ||
                              part.type === 'tool-invocation',
                          )
                          .map(
                            (
                              part: ReasoningUIPart | ToolInvocationUIPart,
                              partIndex: number,
                            ) =>
                              part.type === 'reasoning' ? (
                                <Box
                                  key={`reasoning-${partIndex}`}
                                  $background="var(--c--theme--colors--greyscale-100)"
                                  $color="var(--c--theme--colors--greyscale-500)"
                                  $padding={{ all: 'sm' }}
                                  $radius="md"
                                  $css="font-size: 0.9em;"
                                >
                                  {part.reasoning}
                                </Box>
                              ) : part.type === 'tool-invocation' &&
                                isCurrentlyStreaming &&
                                isLastAssistantMessageInConversation ? (
                                <ToolInvocationItem
                                  key={`tool-invocation-${partIndex}`}
                                  toolInvocation={part.toolInvocation}
                                  status={status}
                                  hideSearchLoader={true}
                                />
                              ) : null,
                          )}
                      </Box>
                      {message.role === 'assistant' &&
                        !(
                          isLastAssistantMessageInConversation &&
                          status === 'streaming'
                        ) && (
                          <Box
                            $css="color: #222631; font-size: 12px;"
                            $direction="row"
                            $align="center"
                            $justify="space-between"
                            $gap="6px"
                            $margin={{ top: 'base' }}
                          >
                            <Box $direction="row" $gap="4px">
                              <Box
                                $direction="row"
                                $align="center"
                                $gap="4px"
                                className="c__button--neutral action-chat-button"
                                onClick={() => copyToClipboard(message.content)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    copyToClipboard(message.content);
                                  }
                                }}
                                role="button"
                                tabIndex={0}
                              >
                                <Icon
                                  iconName="content_copy"
                                  $theme="greyscale"
                                  $variation="550"
                                  $size="16px"
                                  className="action-chat-button-icon"
                                />
                                {!isMobile && (
                                  <Text $theme="greyscale" $variation="550">
                                    {t('Copy')}
                                  </Text>
                                )}
                              </Box>
                              {message.parts?.some(
                                (part) => part.type === 'source',
                              ) &&
                                (() => {
                                  const sourceCount =
                                    message.parts?.filter(
                                      (part) => part.type === 'source',
                                    ).length || 0;
                                  return (
                                    <Box
                                      $direction="row"
                                      $align="center"
                                      $gap="4px"
                                      className={`c__button--neutral action-chat-button ${isSourceOpen === message.id ? 'action-chat-button--open' : ''}`}
                                      onClick={() => openSources(message.id)}
                                      onKeyDown={(e) => {
                                        if (
                                          e.key === 'Enter' ||
                                          e.key === ' '
                                        ) {
                                          e.preventDefault();
                                          openSources(message.id);
                                        }
                                      }}
                                      role="button"
                                      tabIndex={0}
                                    >
                                      <Icon
                                        iconName="book"
                                        $theme="greyscale"
                                        $variation="550"
                                        $size="16px"
                                        className="action-chat-button-icon"
                                      />
                                      <Text
                                        $theme="greyscale"
                                        $variation="550"
                                        $weight="500"
                                        $size="12px"
                                      >
                                        {t('Show')} {sourceCount}{' '}
                                        {sourceCount !== 1
                                          ? t('sources')
                                          : t('source')}
                                      </Text>
                                    </Box>
                                  );
                                })()}
                            </Box>
                            <Box $direction="row" $gap="4px">
                              {/* We should display the button, but disabled if no trace linked */}
                              {conversationId &&
                                message.id &&
                                message.id.startsWith('trace-') && (
                                  <FeedbackButtons
                                    conversationId={conversationId}
                                    messageId={message.id}
                                  />
                                )}
                            </Box>
                          </Box>
                        )}
                      {message.parts &&
                        isSourceOpen === message.id &&
                        (() => {
                          const sourceParts = message.parts.filter(
                            (part): part is SourceUIPart =>
                              part.type === 'source',
                          );
                          return (
                            <Box
                              $css={`
                              animation: fade-in 0.2s ease-out;
                            `}
                            >
                              <SourceItemList
                                parts={sourceParts}
                                getMetadata={getMetadata}
                              />
                            </Box>
                          );
                        })()}
                    </Box>
                  </Box>
                </Box>
              );
            })}
          </Box>
        )}
        {(status !== 'ready' && status !== 'streaming' && status !== 'error') ||
        isUploadingFiles ? (
          <Box
            $direction="row"
            $align="start"
            $gap="6px"
            $width="100%"
            $maxWidth="750px"
            $margin={{ all: 'auto', top: 'base', bottom: '0' }}
            $padding={{ left: '13px', bottom: 'md' }}
            $css={`
              ${streamingMessageHeight ? `min-height: ${streamingMessageHeight}px;` : 'auto'}
            `}
          >
            <Loader />
            <Text $variation="600" $size="md">
              {isUploadingFiles ? t('Uploading files...') : t('Thinking...')}
            </Text>
          </Box>
        ) : null}
        {status === 'error' && (
          <ChatError
            hasLastSubmission={!!lastSubmissionRef.current}
            onRetry={handleRetry}
          />
        )}
      </Box>
      <Box
        $css={`
          position: relative;
          bottom: ${isMobile ? '8px' : '20px'};
          margin: auto;
          background-color: white;
          z-index: 1000;
        `}
        $gap="6px"
        $height="auto"
        $width="100%"
        $margin={{ all: 'auto', top: 'base' }}
      >
        <InputChat
          messagesLength={messages.length}
          input={input}
          handleInputChange={handleInputChange}
          handleSubmit={handleSubmitWrapper}
          status={status}
          files={files}
          onScrollToBottom={scrollToBottom}
          setFiles={setFiles}
          containerRef={chatContainerRef}
          onStop={handleStop}
          forceWebSearch={forceWebSearch}
          onToggleWebSearch={toggleWebSearch}
          selectedModel={selectedModel}
          onModelSelect={handleModelSelect}
          isUploadingFiles={isUploadingFiles}
        />
      </Box>
      <Modal
        isOpen={!!chatErrorModal}
        onClose={() => {
          setChatErrorModal(null);
        }}
        title={chatErrorModal?.title}
        hideCloseButton={true}
        closeOnClickOutside={true}
        closeOnEsc={true}
        size={ModalSize.MEDIUM}
      >
        <Text>{chatErrorModal?.message}</Text>
      </Modal>
    </Box>
  );
};
