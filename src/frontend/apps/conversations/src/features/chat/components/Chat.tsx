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
  const { isDesktop } = useResponsiveStore();

  const streamProtocol = 'data'; // or 'text'
  const [forceWebSearch, setForceWebSearch] = useState(false);
  const apiUrl = `chats/${initialConversationId}/conversation/?protocol=${streamProtocol}`;

  const router = useRouter();
  const [files, setFiles] = useState<FileList | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [conversationId, setConversationId] = useState(initialConversationId);
  const [chatErrorModal, setChatErrorModal] = useState<{
    title: string;
    message: string;
  } | null>(null);
  const [isSourceOpen, setIsSourceOpen] = useState<string | null>(null);

  // Définir la ref globale pour le hook useChatScroll
  useEffect(() => {
    setChatContainerRef(chatContainerRef);
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

    const response = await fetchAPI(`chats/${conversationId}/stop-steaming/`, {
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
    setForceWebSearch((prev) => {
      const newValue = !prev;
      // Update global state for the fetch adapter
      (window as { globalForceWebSearch?: boolean }).globalForceWebSearch =
        newValue;
      return newValue;
    });
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

  useEffect(() => {
    if (chatContainerRef.current) {
      // Find the last user message
      const userMessages = messages.filter((msg) => msg.role === 'user');
      const lastUserMessage = userMessages[userMessages.length - 1];

      if (lastUserMessage) {
        // Find the element of the last user message
        const messageElements =
          chatContainerRef.current.querySelectorAll('[data-message-id]');
        const lastUserMessageElement = Array.from(messageElements).find(
          (el) => el.getAttribute('data-message-id') === lastUserMessage.id,
        );

        if (lastUserMessageElement) {
          // Scroll to position the last user message at the very top
          const messageTop = (lastUserMessageElement as HTMLElement).offsetTop;

          chatContainerRef.current.scrollTo({
            top: messageTop,
            behavior: 'auto',
          });
        }
      } else {
        scrollToBottom();
      }
    }
  }, [messages, hasInitialized, scrollToBottom]);

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
          @keyframes fadeIn {
            from {
              opacity: 0;
            }
            to {
              opacity: 1;
            }
          }
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
          height: ${messages.length > 1 ? 'calc(100vh - 62px)' : '0'}; 
          max-height: ${messages.length > 1 ? 'calc(100vh - 62px)' : '0'}; 
        `}
      >
        {messages.length > 0 && (
          <Box>
            {messages.map((message) => (
              <Box
                key={message.id}
                data-message-id={message.id}
                $css={`
                display: flex;
                  width: 100%;
                  margin: auto;
                  padding-left: 12px;
                  max-width: 750px;
                  text-align: ${message.role === 'user' ? 'right' : 'left'};
                  flex-direction: ${message.role === 'user' ? 'row-reverse' : 'row'};
                `}
              >
                <Box
                  $gap="2"
                  $radius="8px"
                  $padding={`${message.role === 'user' ? '12px' : '0'}`}
                  $margin={{ vertical: 'base' }}
                  $background={`${message.role === 'user' ? '#EEF1F4' : 'white'}`}
                >
                  {message.content && (
                    <Markdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        // Custom components for Markdown rendering
                        // eslint-disable-next-line @typescript-eslint/no-unused-vars
                        p: ({ node, ...props }) => <Text {...props} />,
                      }}
                    >
                      {message.content}
                    </Markdown>
                  )}
                  <Box $direction="column" $gap="2">
                    {message.parts
                      ?.filter(
                        (part) =>
                          part.type === 'reasoning' ||
                          part.type === 'tool-invocation',
                      )
                      .map((part: ReasoningUIPart | ToolInvocationUIPart) =>
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
                        ) : part.type === 'tool-invocation' ? (
                          <ToolInvocationItem
                            toolInvocation={part.toolInvocation}
                          />
                        ) : null,
                      )}
                    {/* Show attachments if present */}
                    {message.experimental_attachments?.map(
                      (attachment: Attachment, index: number) =>
                        attachment.contentType?.includes('text/') ||
                        attachment.contentType?.includes('image/') ? (
                          <div
                            key={`${message.id}-${index}`}
                            style={{
                              display: 'block',
                              width: 'auto',
                              fontSize: 12,
                              borderRadius: 8,
                              color: '#888',
                            }}
                          >
                            {attachment.name}
                          </div>
                        ) : null,
                    )}
                  </Box>
                  {message.role !== 'user' && (
                    <Box
                      $css="color: #626A80; font-size: 12px;"
                      $direction="row"
                      $align="center"
                      $gap="6px"
                      $margin={{ top: 'base' }}
                    >
                      <Box
                        $direction="row"
                        $align="center"
                        $gap="4px"
                        $css="
                      cursor: pointer;
                      z-index: 100;
                      font-size: 12px;
                      padding: 2px 8px;
                      margin-left: -8px;
                      transition: background-color 0.4s;
                      border-radius: 4px;

                      &:hover {
                        background-color: #EEF1F4 !important;
                      }
                    "
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
                          $variation="600"
                          $size="16px"
                        />
                        {isDesktop && (
                          <Text $color="#626A80" $weight="500">
                            {t('Copy')}
                          </Text>
                        )}
                      </Box>
                      {message.parts?.some(
                        (part) => part.type === 'source',
                      ) && (
                        <Box
                          $direction="row"
                          $align="center"
                          $gap="4px"
                          $css="
                        cursor: pointer;
                        z-index: 100;
                        font-size: 12px;
                        padding: 2px 8px;
                        margin-left: -8px;
                        transition: background-color 0.4s;
                        border-radius: 4px;

                        &:hover {
                          background-color: #EEF1F4 !important;
                        }
                      "
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
                            $variation="600"
                            $size="16px"
                          />
                          {isDesktop && (
                            <Text $color="#626A80" $weight="500">
                              {t('Show sources')}
                            </Text>
                          )}
                        </Box>
                      )}
                    </Box>
                  )}
                  {message.parts && isSourceOpen === message.id && (
                    <SourceItemList
                      parts={message.parts.filter(
                        (part): part is SourceUIPart => part.type === 'source',
                      )}
                    />
                  )}
                </Box>
              </Box>
            ))}
          </Box>
        )}
        {(status === 'streaming' || status === 'submitted') && (
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
          bottom: 20px;
          margin: auto;
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
