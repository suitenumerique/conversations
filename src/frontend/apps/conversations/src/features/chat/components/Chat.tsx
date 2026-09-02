import { Button, Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import { InfiniteData, useQueryClient } from '@tanstack/react-query';
import {
  FileUIPart,
  SourceUrlUIPart,
  UIMessage,
  getToolName,
  isToolUIPart,
} from 'ai';
import 'katex/dist/katex.min.css'; // `rehype-katex` does not import the CSS for you
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import {
  APIError,
  errorCauses,
  fetchAPI,
  isRateLimitError,
  rateLimitMessage,
} from '@/api';
import { Box, HorizontalSeparator, Icon, Loader, Text } from '@/components';
import { useConfig } from '@/core';
import { useProjectAttachments } from '@/features/attachments/api/useProjectAttachments';
import { useReindexProjectAttachment } from '@/features/attachments/api/useReindexProjectAttachment';
import { useUploadFile } from '@/features/attachments/hooks/useUploadFile';
import {
  ImagesSkippedEventKind,
  stampImagesSkippedOnLatestUserMessage,
  useChat,
} from '@/features/chat/api/useChat';
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
import { ChatError, ChatErrorType } from '@/features/chat/components/ChatError';
import { ImageProcessingUnavailableBanner } from '@/features/chat/components/ImageProcessingUnavailableBanner';
import { InputChat } from '@/features/chat/components/InputChat';
import { MessageItem } from '@/features/chat/components/MessageItem';
import { SourceItemList } from '@/features/chat/components/SourceItemList';
import {
  STATUS_LINK_KINDS,
  getReindexErrorMessage,
} from '@/features/chat/components/reindexErrorMessages';
import { useSourcePanelAnchor } from '@/features/sources-panel';
import { useClipboard } from '@/hook';
import { useResponsiveStore } from '@/stores';

import { useSourceMetadataCache } from '../hooks';
import { useAprilFools } from '../hooks/useAprilFools';
import { useChatPreferencesStore } from '../stores/useChatPreferencesStore';
import { usePendingChatStore } from '../stores/usePendingChatStore';
import { useScrollStore } from '../stores/useScrollStore';

const PROVIDER_ERROR_CODES = new Set<ChatErrorType>([
  'model_unavailable',
  'model_rate_limited',
  'model_connection_error',
  'model_not_found',
  'model_wrong_type',
  'model_busy',
  'summarization_failed',
]);

const IMAGES_BANNER_STORAGE_PREFIX = 'conversations:images-banner-dismissed:';

const imagesBannerStorageKey = (conversationId: string) =>
  `${IMAGES_BANNER_STORAGE_PREFIX}${conversationId}`;

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
  const { data: config } = useConfig();
  const statusPageUrl = config?.STATUS_PAGE_URL;
  const copyToClipboard = useClipboard();
  const { isMobile, isDesktop } = useResponsiveStore();
  const sourcesPanelAnchorEl = useSourcePanelAnchor();

  const {
    forceWebSearch,
    toggleForceWebSearch,
    selectedModelHrid,
    setSelectedModelHrid,
    setSourcesPanelOpen,
  } = useChatPreferencesStore();

  const { data: llmConfig } = useLLMConfiguration();
  const [selectedModel, setSelectedModel] = useState<LLMModel | null>(null);

  const [conversationId, setConversationId] = useState(initialConversationId);
  const apiUrl = conversationId
    ? `chats/${conversationId}/conversation/`
    : 'chats/conversation/';

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

  const navigate = useNavigate();
  const [files, setFiles] = useState<FileList | null>(null);
  const [isUploadingFiles, setIsUploadingFiles] = useState(false);
  // Project of an already-loaded conversation (new chats use pendingProjectId).
  const [conversationProjectId, setConversationProjectId] = useState<
    string | null
  >(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [chatErrorModal, setChatErrorModal] = useState<{
    title: string;
    message: React.ReactNode;
  } | null>(null);
  const [chatErrorType, setChatErrorType] = useState<ChatErrorType>('generic');

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
    useState<UIMessage[] | undefined>(undefined);
  // True when the pinned model is text-only and any image exists in the
  // conversation (project or history). Drives the "image processing
  // unavailable" banner above the input box.
  const [imagesSkipped, setImagesSkipped] = useState<boolean>(false);
  const [imagesBannerDismissed, setImagesBannerDismissed] =
    useState<boolean>(false);
  const [pendingFirstMessage, setPendingFirstMessage] = useState<{
    input: string;
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
  // Conversation the chat instance currently holds messages for, so a real
  // switch (A -> B) can be told apart from the other reasons the effect below
  // re-runs.
  const loadedConversationIdRef = useRef(initialConversationId);
  const lastSubmissionRef = useRef<{
    input: string;
    files: FileList | null;
  } | null>(null);
  // Whether anything has been sent into the conversation currently loaded. Once
  // it has, the client is authoritative and a fetched snapshot must not replace
  // it. Reset when the conversation changes, below.
  const hasSentRef = useRef(false);
  // The history fetch currently in flight, so a submission can wait for it
  // instead of racing it. Never rejects: fetchInitialMessages catches.
  const historyFetchRef = useRef<Promise<void> | null>(null);

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

  // Surface a notice while the active project still has files being indexed:
  // their content isn't searchable yet, so a message sent now gets an answer
  // that ignores them. Sending stays allowed - the banner states the tradeoff
  // and the user decides. `useProjectAttachments` polls until indexing settles.
  const activeProjectId =
    conversationProjectId ?? pendingProjectId ?? undefined;
  const { data: projectAttachments } = useProjectAttachments(activeProjectId);
  const isIndexingFiles =
    projectAttachments?.some((a) => a.index_state === 'indexing') ?? false;

  // Files whose last indexing attempt failed: they stay usable/downloadable but
  // aren't searchable, so surface an aggregate notice with a retry action.
  const failedIndexingIds = useMemo(
    () =>
      (projectAttachments ?? [])
        .filter((a) => a.index_state === 'failed')
        .map((a) => a.id),
    [projectAttachments],
  );
  const reindexAttachment = useReindexProjectAttachment(activeProjectId ?? '');
  const handleRetryFailedIndexing = useCallback(() => {
    reindexAttachment.mutate(failedIndexingIds);
  }, [failedIndexingIds, reindexAttachment]);

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
      const maxSize = config?.attachment_max_size;
      setChatErrorModal({
        title: t('Upload Error'),
        message: maxSize ? (
          <Text>
            {t(
              'Failed to upload file. It may be due to the attachment size. Max size: {{maxSize}} MB',
              { maxSize },
            )}
          </Text>
        ) : (
          <Text>
            {t('Failed to upload file. It may be due to the attachment size.')}
          </Text>
        ),
      });
    }
  }, [isErrorAttachment, errorAttachment, config?.attachment_max_size, t]);

  // Handle errors from the chat API
  const onErrorChat = (error: Error) => {
    if (error.message === 'attachment_summary_not_supported') {
      setChatErrorModal({
        title: t('Attachment summary not supported'),
        message: <Text>{t('The summary feature is not supported yet.')}</Text>,
      });
      return;
    }

    if (PROVIDER_ERROR_CODES.has(error.message as ChatErrorType)) {
      setChatErrorType(error.message as ChatErrorType);
    } else {
      setChatErrorType('generic');
    }

    console.error('Chat error:', error);
  };

  // The input lives here now: v5's useChat no longer owns it.
  const [input, setInput] = useState('');
  const handleInputChange = useCallback(
    (event: ChangeEvent<HTMLTextAreaElement | HTMLInputElement>) =>
      setInput(event.target.value),
    [],
  );

  // Deliberately not memoized: the hook keeps the latest handler in a ref, so a
  // fresh closure each render is what keeps `setMessages` pointing at the
  // current conversation's chat.
  const onImagesSkipped = (kind: ImagesSkippedEventKind) => {
    if (kind === 'chat_notice') {
      setImagesSkipped(true);
    } else {
      setMessages(stampImagesSkippedOnLatestUserMessage);
    }
  };

  const {
    messages,
    sendMessage,
    status,
    stop: stopChat,
    setMessages,
    cooldownUntil,
  } = useChat({
    // `useChat` rebuilds the chat whenever its id differs from the instance's,
    // and an instance with no id gets a generated one - so `undefined` never
    // matches and the new-chat screen would rebuild on every render.
    id: conversationId ?? 'new',
    messages: initialConversationMessages,
    api: apiUrl,
    onError: onErrorChat,
    onImagesSkipped,
  });

  const stopGeneration = async () => {
    await stopChat();

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
    event.preventDefault();
    void submitMessage();
  };

  const handleRetry = () => {
    if (!lastSubmissionRef.current || !setMessages) {
      return;
    }

    const { input: lastInput, files: lastFiles } = lastSubmissionRef.current;

    // Drop the whole failed turn - the last user message and anything the
    // failed attempt produced after it - because the resubmit below adds the
    // question back. Removing just the last assistant message deleted the
    // *previous*, successful answer whenever the attempt failed before
    // producing one, and left the question on screen twice.
    const lastUserIndex = messages.findLastIndex((msg) => msg.role === 'user');
    if (lastUserIndex !== -1) {
      setMessages(messages.slice(0, lastUserIndex));
    }

    retryOriginalInputRef.current = input;
    retryOriginalFilesRef.current = files;
    setInput(lastInput);
    setFiles(lastFiles);
    setShouldRetry(true);
  };

  // Précharger les métadonnées des sources dès que les messages arrivent
  useEffect(() => {
    messages.forEach((message) => {
      if (message.parts) {
        const sourceParts = message.parts.filter(
          (part): part is SourceUrlUIPart => part.type === 'source-url',
        );
        sourceParts.forEach((part) => {
          void prefetchMetadata(part.url);
        });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  const openSources = useCallback(
    (messageId: string) => {
      setIsSourceOpen((prev) => {
        const next = prev === messageId ? null : messageId;
        setSourcesPanelOpen(next !== null);
        return next;
      });
    },
    [setSourcesPanelOpen],
  );

  useEffect(() => {
    setIsSourceOpen(null);
    setSourcesPanelOpen(false);
  }, [initialConversationId, setSourcesPanelOpen]);

  const selectedSourceParts = useMemo(() => {
    if (!isSourceOpen) {
      return [];
    }
    const sourceMessage = messages.find(
      (message) => message.id === isSourceOpen,
    );
    if (!sourceMessage?.parts) {
      return [];
    }
    return sourceMessage.parts.filter(
      (part): part is SourceUrlUIPart => part.type === 'source-url',
    );
  }, [isSourceOpen, messages]);

  const isSourcesPanelOpen =
    Boolean(isSourceOpen) && selectedSourceParts.length > 0;

  const sourcesPanelContent = isSourcesPanelOpen ? (
    <Box
      $direction="column"
      $height="100%"
      $css={`
          background: var(--c--contextuals--background--surface--secondary);
          border-left: 1px solid
            var(--c--contextuals--border--surface--primary);
          overflow-y: auto;
          ${!isDesktop ? 'border-left: none;' : ''}
        `}
    >
      <Box
        $direction="row"
        $justify="space-between"
        $align="center"
        $margin={{ all: 'xs', left: 'sm' }}
      >
        <Text as="h2" $size="lg" $weight="700">
          {selectedSourceParts.length}{' '}
          {selectedSourceParts.length > 1 ? t('Sources') : t('Source')}
        </Text>
        <Button
          color="neutral"
          variant="tertiary"
          onClick={() => {
            setIsSourceOpen(null);
            setSourcesPanelOpen(false);
          }}
          aria-label={t('Close sources panel')}
          icon={
            <Icon
              iconName="close"
              $theme="neutral"
              $variation="550"
              $size="18px"
            />
          }
        />
      </Box>
      <HorizontalSeparator $withPadding={false} />
      <SourceItemList parts={selectedSourceParts} getMetadata={getMetadata} />
    </Box>
  ) : null;

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

  const lastResumeErrorMessageIdRef = useRef<string | null>(null);

  // Show error modal when conversation resume fails to re-index some documents
  useEffect(() => {
    if (status === 'streaming' || status === 'submitted') return;
    const lastAssistant = messages.filter((m) => m.role === 'assistant').pop();
    if (!lastAssistant?.parts) return;
    if (lastAssistant.id === lastResumeErrorMessageIdRef.current) return;
    const resumePart = lastAssistant.parts
      .filter(isToolUIPart)
      .find(
        (p) =>
          getToolName(p) === 'conversation_resume' &&
          p.state === 'output-available',
      );
    if (!resumePart) return;
    const result = resumePart.output as {
      state: string;
      kind?: string;
      failed_documents?: string[];
      error?: string;
    };
    const isFullError = result?.state === 'error';
    const hasPartialFailures = Boolean(result?.failed_documents?.length);
    if (!isFullError && !hasPartialFailures) return;
    lastResumeErrorMessageIdRef.current = lastAssistant.id;
    const showStatusLink =
      isFullError &&
      !!statusPageUrl &&
      !!result.kind &&
      STATUS_LINK_KINDS.has(result.kind);
    setChatErrorModal({
      title: t('Re-indexing Error'),
      message: isFullError ? (
        <Box $direction="row" $align="center" $gap="6px">
          <Text>{getReindexErrorMessage(t, result.kind)}</Text>
          {showStatusLink && (
            <a
              href={statusPageUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={t('Check service status')}
            >
              <Icon iconName="info" $size="1rem" $color="greyscale" />
            </a>
          )}
        </Box>
      ) : (
        <>
          <Text>
            {t(
              "Couldn't restore some of this conversation's documents, so the assistant can't reference them. Please re-upload them to continue:",
            )}
          </Text>
          <ul>
            {(result.failed_documents ?? []).map((doc) => (
              <li key={doc}>{doc}</li>
            ))}
          </ul>
        </>
      ),
    });
  }, [messages, status, statusPageUrl, t]);

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

  // Scroll to bottom when conversation_resume tool appears so the illustration is fully visible
  useEffect(() => {
    const lastAssistant = messages.filter((m) => m.role === 'assistant').pop();
    const hasResumeTool = lastAssistant?.parts
      .filter(isToolUIPart)
      .some(
        (p) =>
          getToolName(p) === 'conversation_resume' &&
          p.state !== 'output-available',
      );
    if (hasResumeTool && chatContainerRef.current) {
      requestAnimationFrame(() => {
        if (chatContainerRef.current) {
          chatContainerRef.current.scrollTo({
            top: chatContainerRef.current.scrollHeight,
            behavior: 'smooth',
          });
        }
      });
    }
  }, [messages]);

  // Synchronize conversationId state with prop when it changes (e.g., after navigation)
  useEffect(() => {
    setConversationId(initialConversationId);
    // Reset input when conversation changes
    if (initialConversationId !== conversationId) {
      setInput('');
      setHasInitialized(false); // Réinitialiser pour permettre le scroll au prochain chargement
    }
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
        setInput(pendingInput);
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
      void submitMessage();
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
      void submitMessage();
      // Restore what the user had typed before the retry took over the input.
      setInput(retryOriginalInputRef.current);
      setFiles(retryOriginalFilesRef.current);

      setShouldRetry(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldRetry, input, files]);

  // Fetch initial conversation messages if initialConversationId is provided and no pending input
  useEffect(() => {
    hasScrolledToBottomOnLoadRef.current = false; // Réinitialiser au début du chargement
    // Navigating between two conversations reuses this component (the route
    // carries no key) and rebuilds the chat instance as soon as the id
    // changes - before the fetch below resolves. Drop the previous messages
    // first, otherwise they are shown under the new conversation and, if the
    // user submits in that window, posted to its endpoint.
    if (loadedConversationIdRef.current !== initialConversationId) {
      loadedConversationIdRef.current = initialConversationId;
      hasSentRef.current = false;
      setInitialConversationMessages(undefined);
      setMessages([]);
    }
    setImagesSkipped(false);
    // Drop the previous conversation's project so its indexing gate can't leak
    // into this one; the getConversation() success below repopulates it. Skip
    // the reset while a pending first message is creating this conversation: the
    // fetch is skipped in that window, so onSuccess is the only setter and the
    // reset would wipe the project it just assigned.
    if (!(initialConversationId && pendingInput)) {
      setConversationProjectId(null);
    }
    let dismissedFromStorage = false;
    if (initialConversationId && typeof window !== 'undefined') {
      try {
        dismissedFromStorage =
          window.localStorage.getItem(
            imagesBannerStorageKey(initialConversationId),
          ) === '1';
      } catch {
        // localStorage unavailable (privacy mode, sandboxed iframe, etc.) — treat as not dismissed.
      }
    }
    setImagesBannerDismissed(dismissedFromStorage);
    let ignore = false;
    async function fetchInitialMessages() {
      if (initialConversationId && !pendingInput) {
        try {
          const conversation = await getConversation({
            id: initialConversationId,
          });
          if (!ignore) {
            // v5 keeps the messages inside the chat instance, which was built
            // when the id changed — before this fetch resolved.
            setInitialConversationMessages(conversation.messages);
            // The server snapshot is only ever the *initial* state. This effect
            // also re-runs when `pendingInput` clears at the end of the
            // new-conversation handoff, and back then the message that was just
            // sent is not persisted yet: applying the snapshot there wiped the
            // user's question until the next reload. Keying on the send rather
            // than on the message list keeps that true no matter which of the
            // two lands first.
            if (!hasSentRef.current) {
              setMessages(conversation.messages);
            }
            setImagesSkipped(conversation.images_skipped ?? false);
            setConversationProjectId(conversation.project?.id ?? null);
            setHasInitialized(true);
          }
        } catch {
          // Optionally handle error (e.g., setInitialConversationMessages([]) or show error)
          if (!ignore) {
            setInitialConversationMessages([]);
            // Same rule as the success branch above: a failed refetch must not
            // clear a conversation the client has already sent into.
            if (!hasSentRef.current) {
              setMessages([]);
            }
            setHasInitialized(true);
          }
        }
      }
    }
    historyFetchRef.current = fetchInitialMessages();
    return () => {
      ignore = true;
    };
    // Only run when initialConversationId or pendingInput changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialConversationId, pendingInput]);

  const dismissImagesBanner = useCallback(() => {
    setImagesBannerDismissed(true);
    if (typeof window !== 'undefined' && conversationId) {
      try {
        window.localStorage.setItem(
          imagesBannerStorageKey(conversationId),
          '1',
        );
      } catch {
        // localStorage unavailable — in-memory dismissal still holds for this session.
      }
    }
  }, [conversationId]);

  const showImagesBanner = imagesSkipped && !imagesBannerDismissed;

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

  const toFileParts = (attachments: Attachment[]): FileUIPart[] =>
    attachments.map((attachment) => ({
      type: 'file',
      url: attachment.url,
      mediaType: attachment.contentType ?? 'application/octet-stream',
      filename: attachment.name,
    }));

  const send = (text: string, attachments: Attachment[]) => {
    hasSentRef.current = true;
    void sendMessage({ text, files: toFileParts(attachments) });
    setInput('');
  };

  // Custom submit to include attachments and handle chat creation
  const submitMessage = async () => {
    // Sending before the history lands would leave the fetched messages
    // unapplied: the snapshot below is only taken as initial state, and the
    // conversation would look empty apart from this new exchange.
    await historyFetchRef.current;

    // Inference-load cooldown: block new messages until the wait elapses.
    if (cooldownUntil && Date.now() < cooldownUntil) {
      return;
    }

    // April Fools' prank on the very first message of a new conversation.
    // Use triggerDeferred so the prank survives the navigate() remount.
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
          message: (
            <Text>{t('Failed to upload files. Please try again.')}</Text>
          ),
        });
        return;
      }
    }

    if (!conversationId) {
      // Save the message and files, then create the chat
      setPendingFirstMessage({ input, attachments, forceWebSearch });
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
            // Carry the project onto the just-created conversation so its
            // indexing banner/gate keep showing after we clear pendingProjectId
            // below (the getConversation refetch that normally repopulates this
            // is skipped while the pending first message is in flight).
            setConversationProjectId(pendingProjectId ?? null);
            setProjectId(null);
            setConversationId(data.id);
            // Update the URL to /chat/<id>
            void navigate(`/chat/${data.id}`);
            // After setting the conversationId, submit the pending message
            setTimeout(() => {
              if (pendingFirstMessage) {
                send(
                  pendingFirstMessage.input,
                  pendingFirstMessage.attachments ?? [],
                );
                setFiles(null);
                if (fileInputRef.current) {
                  fileInputRef.current.value = '';
                }
                setPendingFirstMessage(null);
              }
            }, 0);
          },
          onError: (error) => {
            // The pending store was primed for a navigation that is not going
            // to happen. It has to be cleared: the mount effect above submits
            // whatever it finds there, so leaving the message behind would
            // auto-send it into the next conversation the user opens. The
            // composer still holds the text (this path returns before the
            // message is handed over), so trying again just works.
            clearPendingInput();
            setPendingFirstMessage(null);
            setChatErrorModal({
              title: isRateLimitError(error)
                ? t('Too many conversations')
                : t('Error'),
              message: (
                <Text>
                  {isRateLimitError(error)
                    ? rateLimitMessage(error, t)
                    : t(
                        'Failed to start a new conversation. Please try again.',
                      )}
                </Text>
              ),
            });
          },
        },
      );
      return;
    }

    setChatErrorType('generic');
    lastSubmissionRef.current = { input, files };

    send(input, attachments);
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
          position: relative;
        `}
    >
      <Box
        ref={chatContainerRef}
        $gap="1rem"
        $padding={{ all: 'lg', left: '13px', bottom: '0', right: '0' }}
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
                      chatErrorType={chatErrorType}
                      onRetry={handleRetry}
                      conversationId={conversationId}
                      isSourceOpen={isSourceOpen}
                      isMobile={isMobile}
                      onCopyToClipboard={copyToClipboard}
                      onOpenSources={openSources}
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
                        $maxWidth="var(--chat-content-max-width, 750px)"
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
            $maxWidth="var(--chat-content-max-width, 750px)"
            $margin={{ all: 'auto', top: 'base', bottom: '0' }}
            $padding={{ left: '13px', bottom: 'md' }}
            $css={`
              ${streamingMessageHeight ? `min-height: ${streamingMessageHeight}px;` : 'auto'}
            `}
          >
            <Loader />
            <Text $theme="neutral" $variation="tertiary" $size="md">
              {(() => {
                if (isUploadingFiles) return t('Uploading files...');
                if (isReadingInstructions)
                  return t('Reading project instructions...');
                return t('Thinking...');
              })()}
            </Text>
          </Box>
        ) : null}
        {status === 'error' &&
          !isUploadingFiles &&
          chatErrorType !== 'summarization_failed' && (
            <ChatError
              errorType={chatErrorType}
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
        $gap="0"
        $height="auto"
        $width="100%"
        $margin={{ all: 'auto', top: 'base' }}
      >
        {showImagesBanner && (
          <ImageProcessingUnavailableBanner onDismiss={dismissImagesBanner} />
        )}
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
          isIndexingFiles={isIndexingFiles}
          failedIndexingCount={failedIndexingIds.length}
          onRetryFailedIndexing={handleRetryFailedIndexing}
          isRetryingIndexing={reindexAttachment.isPending}
          errorType={status === 'error' ? chatErrorType : undefined}
          cooldownUntil={cooldownUntil}
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
        {chatErrorModal?.message}
      </Modal>
      {sourcesPanelContent &&
        sourcesPanelAnchorEl &&
        createPortal(sourcesPanelContent, sourcesPanelAnchorEl)}
    </Box>
  );
};
