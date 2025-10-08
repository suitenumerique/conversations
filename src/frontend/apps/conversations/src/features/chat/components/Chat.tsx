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
import { useTranslation } from 'react-i18next';
import Markdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { Box, Icon, Loader, Text } from '@/components';
import { useChat } from '@/features/chat/api/useChat';
import { getConversation } from '@/features/chat/api/useConversation';
import { useCreateChatConversation } from '@/features/chat/api/useCreateConversation';
import {
  LLMModel,
  useLLMConfiguration,
} from '@/features/chat/api/useLLMConfiguration';
import { scoreMessage } from '@/features/chat/api/useScoreMessage';
import { AttachmentList } from '@/features/chat/components/AttachmentList';
import { InputChat } from '@/features/chat/components/InputChat';
import { SourceItemList } from '@/features/chat/components/SourceItemList';
import { ToolInvocationItem } from '@/features/chat/components/ToolInvocationItem';
import { setChatContainerRef } from '@/features/chat/hooks/useChatScroll';
import { useClipboard } from '@/hook';
import { useResponsiveStore } from '@/stores';

import { usePendingChatStore } from '../stores/usePendingChatStore';

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
  const [forceWebSearch, setForceWebSearch] = useState(() => {
    return (
      (window as { globalForceWebSearch?: boolean }).globalForceWebSearch ||
      false
    );
  });

  const { data: llmConfig } = useLLMConfiguration();
  const [selectedModel, setSelectedModel] = useState<LLMModel | null>(() => {
    // Initialize with default model if available
    if (llmConfig?.models) {
      return llmConfig.models.find((model) => model.is_default) || null;
    }
    return null;
  });

  const [conversationId, setConversationId] = useState(initialConversationId);
  const apiUrl = conversationId
    ? `chats/${conversationId}/conversation/?protocol=${streamProtocol}`
    : `chats/conversation/?protocol=${streamProtocol}`;

  useEffect(() => {
    (window as { globalForceWebSearch?: boolean }).globalForceWebSearch =
      forceWebSearch;
  }, [forceWebSearch]);

  // Update selected model when LLM config loads
  useEffect(() => {
    if (llmConfig?.models && !selectedModel) {
      const defaultModel = llmConfig.models.find((model) => model.is_default);
      if (defaultModel) {
        setSelectedModel(defaultModel);
      }
    }
  }, [llmConfig, selectedModel]);

  // Update global model selection
  useEffect(() => {
    (window as { globalSelectedModelHrid?: string }).globalSelectedModelHrid =
      selectedModel?.hrid || undefined;
  }, [selectedModel]);

  const handleModelSelect = (model: LLMModel) => {
    setSelectedModel(model);
  };

  const router = useRouter();
  const [files, setFiles] = useState<FileList | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [chatErrorModal, setChatErrorModal] = useState<{
    title: string;
    message: string;
  } | null>(null);
  const [isSourceOpen, setIsSourceOpen] = useState<string | null>(null);

  // Définir la ref globale pour le hook useChatScroll
  useEffect(() => {
    setChatContainerRef(chatContainerRef);
  }, []);

  // Détecter si l'utilisateur scroll vers le haut
  useEffect(() => {
    const container = chatContainerRef.current;
    if (!container) {
      return;
    }

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;

      if (isAtBottom) {
        setUserScrolledUp(false);
      } else {
        setUserScrolledUp(true);
      }
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  const [initialConversationMessages, setInitialConversationMessages] =
    useState<Message[] | undefined>(undefined);
  const [pendingFirstMessage, setPendingFirstMessage] = useState<{
    event: React.FormEvent<HTMLFormElement>;
    attachments?: FileList | null;
    forceWebSearch?: boolean;
  } | null>(null);
  const [shouldAutoSubmit, setShouldAutoSubmit] = useState(false);
  const [hasInitialized, setHasInitialized] = useState(false);
  const [streamingMessageHeight, setStreamingMessageHeight] = useState<
    number | null
  >(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);

  const { mutate: createChatConversation } = useCreateChatConversation();

  // Zustand store for pending chat state
  const {
    input: pendingInput,
    files: pendingFiles,
    setPendingChat,
    clearPendingChat,
  } = usePendingChatStore();

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
  } = useChat({
    id: conversationId,
    initialMessages: initialConversationMessages,
    api: apiUrl,
    streamProtocol: streamProtocol,
    sendExtraMessageFields: true,
    onError: onErrorChat,
  });

  // Scroll to bottom when new messages arrive
  const scrollToBottom = useCallback(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: hasInitialized ? 'smooth' : 'auto',
      });
    }
  }, [hasInitialized]);

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
    setForceWebSearch((prev) => !prev);
  };

  const handleStop = () => {
    void stopGeneration();
  };

  const handleSubmitWrapper = (event: React.FormEvent<HTMLFormElement>) => {
    void handleSubmit(event);
  };

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

          const thinkingHeight = 90;
          const availableHeight =
            containerHeight - userMessageHeight - thinkingHeight;

          if (streamingMessageHeight !== availableHeight) {
            setStreamingMessageHeight(availableHeight);
          }
        }
      }
    }
  }, [messages, streamingMessageHeight]);

  useEffect(() => {
    if (chatContainerRef.current && messages.length > 0) {
      const userMessages = messages.filter((msg) => msg.role === 'user');
      const assistantMessages = messages.filter(
        (msg) => msg.role === 'assistant',
      );
      const lastMessage = messages[messages.length - 1];

      // Gérer la hauteur de streaming
      if (
        lastMessage &&
        lastMessage.role === 'user' &&
        assistantMessages.length > 0 &&
        status === 'ready'
      ) {
        // Nouveau message user détecté, réinitialiser la hauteur
        setStreamingMessageHeight(null);
      } else if (status === 'streaming' || status === 'submitted') {
        // Calculer la hauteur pendant le streaming
        calculateStreamingHeight();
      }

      if (
        hasInitialized &&
        (status === 'streaming' || status === 'submitted') &&
        !userScrolledUp
      ) {
        const lastUserMessage = userMessages[userMessages.length - 1];
        if (lastUserMessage) {
          const messageElements =
            chatContainerRef.current.querySelectorAll('[data-message-id]');
          const lastUserMessageElement = Array.from(messageElements).find(
            (el) => el.getAttribute('data-message-id') === lastUserMessage.id,
          );

          if (lastUserMessageElement) {
            const messageTop = (lastUserMessageElement as HTMLElement)
              .offsetTop;
            chatContainerRef.current.scrollTo({
              top: messageTop,
              behavior: 'smooth',
            });
          }
        }
      }
    }
  }, [
    messages,
    status,
    hasInitialized,
    calculateStreamingHeight,
    userScrolledUp,
  ]);

  // Synchronize conversationId state with prop when it changes (e.g., after navigation)
  useEffect(() => {
    setConversationId(initialConversationId);
    // Reset input when conversation changes
    if (initialConversationId !== conversationId) {
      handleInputChange({
        target: { value: '' },
      } as React.ChangeEvent<HTMLTextAreaElement>);
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
        } as React.ChangeEvent<HTMLInputElement>;
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
      } as unknown as React.FormEvent<HTMLFormElement>;
      void handleSubmit(syntheticFormEvent);
      setShouldAutoSubmit(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAutoSubmit, input, files]);

  // Fetch initial conversation messages if initialConversationId is provided and no pending input
  useEffect(() => {
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

            setTimeout(() => {
              if (chatContainerRef.current) {
                chatContainerRef.current.scrollTo({
                  top: chatContainerRef.current.scrollHeight,
                  behavior: 'auto',
                });
              }
            }, 100);
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

  // Custom handleSubmit to include attachments and handle chat creation
  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    // Convert files to base64 if they exist
    let attachments: Attachment[] = [];
    if (files && files.length > 0) {
      attachments = await Promise.all(
        Array.from(files).map(async (file) => {
          return new Promise<Attachment>((resolve) => {
            const reader = new FileReader();
            reader.onload = () => {
              resolve({
                name: file.name,
                contentType: file.type,
                url: reader.result as string,
              });
            };
            reader.readAsDataURL(file);
          });
        }),
      );
    }

    if (!conversationId) {
      // Save the event and files, then create the chat
      setPendingFirstMessage({ event, attachments: files, forceWebSearch });
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
        $overflow="scroll"
        $css={`
          flex-basis: auto;
          flex-grow: 1;
          position: relative;
          margin-bottom: 0;
          height: ${messages.length > 0 ? 'calc(100vh - 62px)' : '0'}; 
          max-height: ${messages.length > 0 ? 'calc(100vh - 62px)' : '0'}; 
        `}
      >
        {messages.length > 0 && (
          <Box>
            {messages.map((message, index) => {
              const isLastAssistantMessageInConversation =
                message.role === 'assistant' &&
                index ===
                  messages.findLastIndex((msg) => msg.role === 'assistant');
              const shouldApplyStreamingHeight =
                isLastAssistantMessageInConversation && streamingMessageHeight;
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
                    color: var(--c--theme--colors--greyscale-850);
                    padding-left: 12px;
                    padding-right: 12px;
                    max-width: 750px;
                    text-align: left;
                    flex-direction: ${message.role === 'user' ? 'row-reverse' : 'row'};
                    ${shouldApplyStreamingHeight ? `min-height: ${streamingMessageHeight + 70}px;` : ''}
                  `}
                >
                  <Box $display="block">
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
                      $maxWidth="100%"
                      $padding={`${message.role === 'user' ? '12px' : '0'}`}
                      $margin={{ vertical: 'base' }}
                      $background={`${message.role === 'user' ? '#EEF1F4' : 'white'}`}
                      $css={`
                      display: inline-block;
                      float: right;`}
                    >
                      {/* Message content */}
                      {message.content && (
                        <Box $padding={{ all: 'xxs' }}>
                          <Markdown
                            remarkPlugins={[remarkGfm, remarkMath]}
                            rehypePlugins={[rehypeKatex]}
                            components={{
                              // Custom components for Markdown rendering
                              // eslint-disable-next-line @typescript-eslint/no-unused-vars
                              p: ({ node, ...props }) => (
                                <Text
                                  $css="display: block"
                                  $theme="greyscale"
                                  $variation="850"
                                  {...props}
                                />
                              ),
                            }}
                          >
                            {message.content}
                          </Markdown>
                        </Box>
                      )}

                      <Box $direction="column" $gap="2">
                        {message.parts
                          ?.filter(
                            (part) =>
                              part.type === 'reasoning' ||
                              part.type === 'tool-invocation',
                          )
                          .map(
                            (part: ReasoningUIPart | ToolInvocationUIPart) =>
                              part.type === 'reasoning' ? (
                                <Box
                                  key={part.reasoning}
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
                                  toolInvocation={part.toolInvocation}
                                  status={status}
                                />
                              ) : null,
                          )}
                      </Box>
                      {message.role !== 'user' && !isCurrentlyStreaming && (
                        <Box
                          $css="color: #222631; font-size: 12px;"
                          $direction="row"
                          $align="center"
                          $gap="6px"
                          $margin={{ top: 'base' }}
                        >
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
                                  className={`c__button--neutral action-chat-button ${isSourceOpen ? 'action-chat-button--open' : ''}`}
                                  onClick={() => openSources(message.id)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
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
                                    {t('Show') +
                                      ` ${sourceCount} ` +
                                      t('sources')}
                                  </Text>
                                </Box>
                              );
                            })()}

                          {conversationId &&
                            message.id &&
                            // We should display the button, but disabled if no trace linked
                            message.id.startsWith('trace-') && (
                              <>
                                <Box
                                  $direction="row"
                                  $align="center"
                                  className="c__button--neutral action-chat-button"
                                  onClick={() => {
                                    if (conversationId) {
                                      void scoreMessage({
                                        conversationId,
                                        message_id: message.id,
                                        value: 'positive',
                                      });
                                    }
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      if (conversationId) {
                                        void scoreMessage({
                                          conversationId,
                                          message_id: message.id,
                                          value: 'positive',
                                        });
                                      }
                                    }
                                  }}
                                  role="button"
                                  tabIndex={0}
                                >
                                  <Icon
                                    iconName="thumb_up"
                                    $theme="greyscale"
                                    $variation="550"
                                    $size="16px"
                                    className="action-chat-button-icon"
                                  />
                                </Box>
                                <Box
                                  $direction="row"
                                  $align="center"
                                  className="c__button--neutral action-chat-button"
                                  onClick={() => {
                                    if (conversationId) {
                                      void scoreMessage({
                                        conversationId,
                                        message_id: message.id,
                                        value: 'negative',
                                      });
                                    }
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      if (conversationId) {
                                        void scoreMessage({
                                          conversationId,
                                          message_id: message.id,
                                          value: 'negative',
                                        });
                                      }
                                    }
                                  }}
                                  role="button"
                                  tabIndex={0}
                                >
                                  <Icon
                                    iconName="thumb_down"
                                    $theme="greyscale"
                                    $variation="550"
                                    $size="16px"
                                    className="action-chat-button-icon"
                                  />
                                </Box>
                              </>
                            )}
                        </Box>
                      )}
                      {message.parts && isSourceOpen === message.id && (
                        <SourceItemList
                          parts={message.parts.filter(
                            (part): part is SourceUIPart =>
                              part.type === 'source',
                          )}
                        />
                      )}
                    </Box>
                  </Box>
                </Box>
              );
            })}
          </Box>
        )}
        {status !== 'ready' && status !== 'streaming' && (
          <Box
            $direction="row"
            $align="center"
            $gap="6px"
            $width="100%"
            $maxWidth="750px"
            $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
            $padding={{ left: '13px' }}
          >
            <Loader />
            <Text $variation="600" $size="md">
              {t('Thinking...')}
            </Text>
          </Box>
        )}
      </Box>
      <Box
        $css={`
          position: relative;
          bottom: ${isMobile ? '8px' : '20px'};
          margin: auto;
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
          setFiles={setFiles}
          onScrollToBottom={scrollToBottom}
          containerRef={chatContainerRef}
          onStop={handleStop}
          forceWebSearch={forceWebSearch}
          onToggleWebSearch={toggleWebSearch}
          selectedModel={selectedModel}
          onModelSelect={handleModelSelect}
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
