import { Message, SourceUIPart } from '@ai-sdk/ui-utils';
import { Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import { InfiniteData, useQueryClient } from '@tanstack/react-query';
import 'katex/dist/katex.min.css'; // `rehype-katex` does not import the CSS for you
import { useRouter } from 'next/router';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { Box, Loader, Text } from '@/components';
import { useUploadFile } from '@/features/attachments/hooks/useUploadFile';
import { useChat } from '@/features/chat/api/useChat';
import { getConversation } from '@/features/chat/api/useConversation';
import { useCreateChatConversation } from '@/features/chat/api/useCreateConversation';
import {
  LLMModel,
  useLLMConfiguration,
} from '@/features/chat/api/useLLMConfiguration';
import {
  KEY_LIST_PROJECT,
  ProjectsResponse,
} from '@/features/chat/api/useProjects';
import { ChatError } from '@/features/chat/components/ChatError';
import { InputChat } from '@/features/chat/components/InputChat';
import { MessageItem } from '@/features/chat/components/MessageItem';
import { useClipboard } from '@/hook';
import { useResponsiveStore } from '@/stores';

import { useSourceMetadataCache } from '../hooks';
import { useAprilFools } from '../hooks/useAprilFools';
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
        setSelectedModelHrid(modelToSelect.hrid);
      }
    }
  }, [llmConfig, selectedModel, selectedModelHrid, setSelectedModelHrid]);

  const handleModelSelect = (model: LLMModel) => {
    setSelectedModel(model);
    setSelectedModelHrid(model.hrid);
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
  const queryClient = useQueryClient();
  const [isReadingInstructions, setIsReadingInstructions] = useState(false);
  const readingInstructionsStartRef = useRef<number>(0);
  const aprilFools = useAprilFools();

  // Zustand store for pending chat state
  const {
    input: pendingInput,
    files: pendingFiles,
    projectId: pendingProjectId,
    hasProjectInstructions,
    setPendingChat,
    setProjectId,
    setHasProjectInstructions,
    clearPendingInput,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  const openSources = useCallback((messageId: string) => {
    // Source-parts guard is handled at the call site (MessageItem only shows the button when sourceParts.length > 0),
    // so we just toggle it here.
    setIsSourceOpen((prev) => (prev === messageId ? null : messageId));
  }, []);

  // Memoize the last assistant message index to avoid recalculating in render
  const lastAssistantMessageIndex = useMemo(() => {
    return messages.findLastIndex((msg) => msg.role === 'assistant');
  }, [messages]);

  // Memoize whether this is the first conversation (2 or fewer messages)
  const isFirstConversationMessage = useMemo(() => {
    return messages.length <= 2;
  }, [messages.length]);

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

          const availableHeight = containerHeight - (userMessageHeight + 130);

          setStreamingMessageHeight((prev) => {
            if (prev === null || Math.abs(prev - availableHeight) > 10) {
              return availableHeight;
            }
            return prev;
          });
        }
      }
    }
  }, [messages]);

  // Clear "reading instructions" once streaming begins or on error, with minimum display time
  useEffect(() => {
    if (isReadingInstructions) {
      if (status === 'error') {
        setIsReadingInstructions(false);
      } else if (status === 'streaming') {
        const elapsed = Date.now() - readingInstructionsStartRef.current;
        const remaining = Math.max(0, 1500 - elapsed);
        const timer = setTimeout(
          () => setIsReadingInstructions(false),
          remaining,
        );
        return () => clearTimeout(timer);
      }
    }
  }, [status, isReadingInstructions]);

  // Détecter l'arrivée d'un nouveau message user et retirer la hauteur de l'ancien
  useEffect(() => {
    if (status === 'streaming') {
      return;
    }

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
  }, [messages, status]);

  useEffect(() => {
    if (status === 'submitted' || status === 'streaming') {
      calculateStreamingHeight();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

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
      const container = chatContainerRef.current;
      const messageElement = container?.querySelector(
        `[data-message-id="${lastUserMessage.id}"]`,
      );

      if (container && messageElement) {
        const targetTop = Math.max(
          0,
          (messageElement as HTMLElement).offsetTop - 100,
        );
        container.scrollTo({ top: targetTop, behavior: 'smooth' });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialConversationId, conversationId]);

  // On mount, if there is pending input/files, initialize state and set flag
  useEffect(() => {
    if (
      (pendingInput && pendingInput.trim()) ||
      (pendingFiles && pendingFiles.length > 0)
    ) {
      if (hasProjectInstructions) {
        readingInstructionsStartRef.current = Date.now();
        setIsReadingInstructions(true);
      }
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
    }
    // Clear input/files but keep projectId alive until conversation is created
    clearPendingInput();
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

  // Check if the current project has custom LLM instructions
  const checkProjectHasInstructions = useCallback(() => {
    if (!pendingProjectId) return false;
    const projectsData = queryClient.getQueryData<
      InfiniteData<ProjectsResponse>
    >([KEY_LIST_PROJECT, { page: 1 }]);
    const project = projectsData?.pages
      .flatMap((page) => page.results)
      .find((p) => p.id === pendingProjectId);
    return !!project?.llm_instructions?.trim();
  }, [pendingProjectId, queryClient]);

  // Custom handleSubmit to include attachments and handle chat creation
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    // April Fools' prank on the very first message of a new conversation.
    // Use triggerDeferred so the prank survives the router.push() remount.
    if (messages.length === 0) {
      aprilFools.triggerDeferred();
    }

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
      if (checkProjectHasInstructions()) {
        setHasProjectInstructions(true);
      }
      void createChatConversation(
        {
          title: input.length > 100 ? `${input.slice(0, 97)}...` : input,
          ...(pendingProjectId && { project: pendingProjectId }),
        },
        {
          onSuccess: (data) => {
            setProjectId(null);
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
          z-index: 1;
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
          max-height: ${messages.length > 0 ? 'calc(100vh - 75px)' : '0'};
        `}
      >
        {messages.length > 0 && (
          <Box>
            {messages.map((message, index) => {
              // Hide the real assistant response while the prank is still streaming
              const hideAssistant =
                aprilFools.isActive &&
                message.role === 'assistant' &&
                index === messages.length - 1;

              return (
                <React.Fragment key={message.id}>
                  {hideAssistant ? null : (
                    <MessageItem
                      message={message}
                      isLastMessage={index === messages.length - 1}
                      isLastAssistantMessage={
                        message.role === 'assistant' &&
                        index === lastAssistantMessageIndex
                      }
                      isFirstConversationMessage={isFirstConversationMessage}
                      streamingMessageHeight={streamingMessageHeight}
                      status={status}
                      conversationId={conversationId}
                      isSourceOpen={isSourceOpen}
                      isMobile={isMobile}
                      onCopyToClipboard={copyToClipboard}
                      onOpenSources={openSources}
                      getMetadata={getMetadata}
                    />
                  )}
                  {/* Inject the prank right after the last user message */}
                  {aprilFools.isActive &&
                    message.role === 'user' &&
                    (index === messages.length - 1 ||
                      index === messages.length - 2) && (
                      <Box
                        $direction="column"
                        $width="100%"
                        $maxWidth="750px"
                        $margin={{ all: 'auto', top: 'base', bottom: '0' }}
                        $padding={{ left: '13px', bottom: 'md' }}
                      >
                        <Text
                          $variation="600"
                          $size="md"
                          $css="white-space: pre-wrap;"
                        >
                          {aprilFools.displayedText}
                        </Text>
                      </Box>
                    )}
                </React.Fragment>
              );
            })}
          </Box>
        )}
        {!aprilFools.isActive &&
        ((status !== 'ready' && status !== 'streaming' && status !== 'error') ||
          isUploadingFiles) ? (
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
              {(() => {
                if (isUploadingFiles) return t('Uploading files...');
                if (isReadingInstructions)
                  return t('Reading project instructions...');
                return t('Thinking...');
              })()}
            </Text>
          </Box>
        ) : null}
        {status === 'error' && !isUploadingFiles && (
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
          background-color: var(--c--contextuals--background--surface--secondary);
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
