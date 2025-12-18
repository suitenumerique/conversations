import { Message, SourceUIPart } from '@ai-sdk/ui-utils';
import { Modal, ModalSize } from '@openfun/cunningham-react';
import { useRouter } from 'next/router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { Box, Loader, Text } from '@/components';
import { useUploadFile } from '@/features/attachments/hooks/useUploadFile';
import { useChat } from '@/features/chat/api/useChat';
import { getConversation } from '@/features/chat/api/useConversation';
import { useCreateChatConversation } from '@/features/chat/api/useCreateConversation';
import { ChatError } from '@/features/chat/components/ChatError';
import { InputChat } from '@/features/chat/components/InputChat';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import { useScrollStore } from '@/features/chat/stores/useScrollStore';
import { useResponsiveStore } from '@/stores';

import { useModelSelection, useSourceMetadataCache } from '../hooks';

import { ChatMessage } from './ChatMessage';

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
  const { isMobile } = useResponsiveStore();
  const streamProtocol = 'data'; // or 'text'

  const { forceWebSearch, toggleForceWebSearch } = useChatPreferencesStore();

  const { selectedModel, handleModelSelect } = useModelSelection();

  // Use custom hook for conversation sync - we'll update it after useChat
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
  const {
    input: pendingInput,
    files: _pendingFiles,
    setPendingChat,
    clearPendingChat: _clearPendingChat,
  } = usePendingChatStore();
  const [hasInitialized, setHasInitialized] = useState(false);

  const [pendingFirstMessage, setPendingFirstMessage] = useState<{
    event: FormEvent<HTMLFormElement>;
    attachments?: Attachment[];
    forceWebSearch?: boolean;
  } | null>(null);
  const [shouldRetry, setShouldRetry] = useState(false);
  const retryOriginalInputRef = useRef<string>('');
  const retryOriginalFilesRef = useRef<FileList | null>(null);
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
  const onErrorChat = useCallback(
    (error: Error) => {
      if (error.message === 'attachment_summary_not_supported') {
        setChatErrorModal({
          title: t('Attachment summary not supported'),
          message: t('The summary feature is not supported yet.'),
        });
      }
      console.error('Chat error:', error);
    },
    [t],
  );

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
    // Ne pas réinitialiser les messages si on est en train de créer une conversation
    initialMessages: pendingFirstMessage
      ? undefined
      : initialConversationMessages,
    api: apiUrl,
    streamProtocol: streamProtocol,
    sendExtraMessageFields: true,
    onError: onErrorChat,
  });

  // Ref pour messages pour éviter de recréer openSources à chaque changement
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

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

  // Custom handleSubmit to include attachments and handle chat creation
  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
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
            onSuccess: (data: { id: string }) => {
              setConversationId(data.id);
              // Update the URL to /chat/[id]/
              void router.push(`/chat/${data.id}/`);
              // Le message sera envoyé via le useEffect qui attend que useChat soit prêt
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
    },
    [
      files,
      conversationId,
      uploadFile,
      t,
      forceWebSearch,
      setPendingChat,
      input,
      createChatConversation,
      setConversationId,
      router,
      baseHandleSubmit,
    ],
  );

  // Synchronize conversationId state with prop when it changes
  useEffect(() => {
    // Ne réinitialiser que si on change vraiment de conversation (pas lors de la création)
    if (
      initialConversationId &&
      initialConversationId !== conversationId &&
      !pendingFirstMessage
    ) {
      setConversationId(initialConversationId);
      // Reset input when conversation changes
      handleInputChange({
        target: { value: '' },
      } as ChangeEvent<HTMLTextAreaElement>);
      setHasInitialized(false);
    } else if (
      !initialConversationId &&
      conversationId &&
      !pendingFirstMessage
    ) {
      // Si on n'a plus d'initialConversationId mais qu'on a un conversationId, ne rien faire
      // (on est peut-être en train de créer une conversation)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialConversationId, conversationId, pendingFirstMessage]);

  useEffect(() => {
    if (
      conversationId &&
      pendingFirstMessage &&
      status === 'ready' &&
      apiUrl.includes(conversationId)
    ) {
      const pending = pendingFirstMessage;

      // Préparer les options avec les attachments
      const options: Record<string, unknown> = {};
      if (pending.attachments && pending.attachments.length > 0) {
        options.experimental_attachments = pending.attachments;
      }

      // Mettre à jour lastSubmissionRef pour le retry
      lastSubmissionRef.current = {
        input,
        files,
        event: pending.event,
        options: Object.keys(options).length > 0 ? options : undefined,
      };

      setPendingFirstMessage(null);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (Object.keys(options).length > 0) {
            baseHandleSubmit(pending.event, options);
          } else {
            baseHandleSubmit(pending.event);
          }

          // Nettoyer les fichiers après l'envoi
          setFiles(null);
          if (fileInputRef.current) {
            fileInputRef.current.value = '';
          }
        });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, status, baseHandleSubmit, pendingFirstMessage, apiUrl]);

  // Fetch initial conversation messages if initialConversationId is provided
  useEffect(() => {
    hasScrolledToBottomOnLoadRef.current = false;
    let ignore = false;
    async function fetchInitialMessages() {
      if (initialConversationId && !pendingInput && !pendingFirstMessage) {
        try {
          const conversation = await getConversation({
            id: initialConversationId,
          });
          if (!ignore) {
            setInitialConversationMessages(conversation.messages);
            setHasInitialized(true);
          }
        } catch {
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
  }, [initialConversationId, pendingInput, pendingFirstMessage]);

  const scrollToBottom = useCallback(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: hasInitialized ? 'smooth' : 'auto',
      });
    }
  }, [hasInitialized]);

  const stopGeneration = useCallback(async () => {
    stopChat();

    if (!conversationId) {
      return;
    }

    const response = await fetchAPI(`chats/${conversationId}/stop-streaming/`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new APIError(
        'Failed to stop the conversation',
        await errorCauses(response),
      );
    }
  }, [stopChat, conversationId]);

  const toggleWebSearch = useCallback(() => {
    toggleForceWebSearch();
  }, [toggleForceWebSearch]);

  const handleStop = useCallback(() => {
    void stopGeneration();
  }, [stopGeneration]);

  const handleSubmitWrapper = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      void handleSubmit(event);
    },
    [handleSubmit],
  );

  // Utiliser un ref pour messages pour éviter de recréer la fonction à chaque changement
  const openSources = useCallback(
    (messageId: string) => {
      if (isSourceOpen === messageId) {
        setIsSourceOpen(null);
        return;
      }
      const message = messagesRef.current.find((msg) => msg.id === messageId);
      if (message?.parts) {
        const sourceParts = message.parts.filter(
          (part) => part.type === 'source',
        );
        if (sourceParts.length > 0) {
          setIsSourceOpen(messageId);
        }
      }
    },
    [isSourceOpen], // Plus besoin de messages dans les dépendances
  );

  // Mémoriser le calcul du dernier index assistant (évite de le recalculer pour chaque message)
  const lastAssistantIndex = useMemo(
    () => messages.findLastIndex((msg) => msg.role === 'assistant'),
    [messages],
  );

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

          const availableHeight = containerHeight - userMessageHeight - 38;

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
  }, [hasInitialized, conversationId, messages.length]);

  const handleRetry = useCallback(() => {
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
  }, [
    lastSubmissionRef,
    setMessages,
    messages,
    input,
    files,
    handleInputChange,
  ]);

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
                message.role === 'assistant' && index === lastAssistantIndex;
              const shouldApplyStreamingHeight = Boolean(
                isLastAssistantMessageInConversation && isLastMessage,
              );
              const isCurrentlyStreaming =
                isLastAssistantMessageInConversation &&
                (status === 'streaming' || status === 'submitted');

              return (
                <ChatMessage
                  key={message.id}
                  message={message}
                  isLastAssistantMessageInConversation={
                    isLastAssistantMessageInConversation
                  }
                  shouldApplyStreamingHeight={shouldApplyStreamingHeight}
                  streamingMessageHeight={streamingMessageHeight}
                  isCurrentlyStreaming={isCurrentlyStreaming}
                  status={isCurrentlyStreaming ? status : 'ready'} // Ne passer le vrai status que si nécessaire
                  isSourceOpen={isSourceOpen}
                  conversationId={conversationId}
                  onOpenSources={openSources}
                  getMetadata={getMetadata}
                />
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
