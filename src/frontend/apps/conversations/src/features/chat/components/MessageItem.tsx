import { Button } from '@gouvfr-lasuite/cunningham-react';
import {
  SourceUrlUIPart,
  ToolUIPart,
  UIMessage,
  getToolName,
  isToolUIPart,
} from 'ai';
import React from 'react';
import { useTranslation } from 'react-i18next';

import CheckmarkIcon from '@/assets/icons/uikit-custom/checkmark.svg?react';
import ClipboardIcon from '@/assets/icons/uikit-custom/clipboard.svg?react';
import SourcesIcon from '@/assets/icons/uikit-custom/sources.svg?react';
import { Box, Loader, Text } from '@/components';
import { useConfig } from '@/core/config';
import { SkippableFileUIPart } from '@/features/chat/api/useChat';
import { AttachmentList } from '@/features/chat/components/AttachmentList';
import { FeedbackButtons } from '@/features/chat/components/FeedbackButtons';
import {
  CompletedMarkdownBlock,
  RawTextBlock,
} from '@/features/chat/components/MessageBlock';
import { MessageEnergyIndicator } from '@/features/chat/components/MessageEnergyIndicator';
import { MoreActionsButton } from '@/features/chat/components/MoreActionsButton';
import { SummarizationError } from '@/features/chat/components/SummarizationError';
import { SummarizationProgress } from '@/features/chat/components/SummarizationProgress';
import { ToolInvocationItem } from '@/features/chat/components/ToolInvocationItem';
import { getMessageCo2Impact } from '@/features/chat/utils/getMessageCo2Impact';
import { getMessageText } from '@/features/chat/utils/getMessageText';

import { ChatErrorType } from './ChatError';

const chatActionIconProps = {
  width: 16,
  height: 16,
  color: 'var(--c--contextuals--content--semantic--neutral--secondary)',
  className: 'action-chat-button-icon',
  style: {
    display: 'block',
    fill: 'var(--c--contextuals--content--semantic--neutral--secondary)',
  } as const,
  'aria-hidden': true,
};

// Memoized blocks list to prevent parent re-renders from causing block remounts
const BlocksList = React.memo(
  ({ blocks, pending }: { blocks: string[]; pending: string }) => (
    <>
      {/* key={index} is safe here: blocks are append-only during streaming
         and a completed block's content never changes once finalized. */}
      {blocks.map((block, index) => (
        <CompletedMarkdownBlock key={index} content={block} />
      ))}
      {pending && <RawTextBlock content={pending} />}
    </>
  ),
  (prev, next) => {
    const lengthChanged = prev.blocks.length !== next.blocks.length;
    const pendingChanged = prev.pending !== next.pending;

    let blocksChanged = false;
    for (let i = 0; i < Math.min(prev.blocks.length, next.blocks.length); i++) {
      if (prev.blocks[i] !== next.blocks[i]) {
        blocksChanged = true;
      }
    }

    if (lengthChanged || pendingChanged || blocksChanged) {
      return false; // needs re-render
    }
    return true;
  },
);
BlocksList.displayName = 'BlocksList';

export interface StreamingContent {
  completedBlocks: string[];
  pending: string;
}

/**
 * Splits content into blocks by double newlines, respecting code fences.
 * Code fences may contain double newlines, so we merge blocks until fences are balanced.
 */
export const splitIntoBlocks = (content: string): string[] => {
  if (!content) {
    return [];
  }

  const rawBlocks = content.split('\n\n');
  const blocks: string[] = [];
  let currentBlock = '';
  let fenceCount = 0;

  for (const rawBlock of rawBlocks) {
    const fences = (rawBlock.match(/```/g) || []).length;

    currentBlock = currentBlock ? currentBlock + '\n\n' + rawBlock : rawBlock;
    fenceCount += fences;

    // Balanced fences = complete block
    if (fenceCount % 2 === 0) {
      if (currentBlock.trim()) {
        blocks.push(currentBlock);
      }
      currentBlock = '';
      fenceCount = 0;
    }
  }

  if (currentBlock.trim()) {
    blocks.push(currentBlock);
  }

  return blocks;
};

/**
 * Splits streaming content into completed blocks (safe and ready to render as markdown)
 * + a pending content (still being streamed, rendered as raw text).
 *
 * A block is considered completed when followed by a double newline.
 * Each block is returned separately to enable independent memoization.
 * NB: it respects code fences (``` ... ```) that may contain double newlines.
 */
export const splitStreamingContent = (content: string): StreamingContent => {
  if (!content) {
    return { completedBlocks: [], pending: '' };
  }

  // Find all code fence positions
  // Note: this counts all ``` occurrences including those inside inline code spans.
  // In practice this is unlikely to cause issues since inline code rarely contains ```.
  const fenceRegex = /```/g;
  const fences: number[] = [];
  let match;
  while ((match = fenceRegex.exec(content)) !== null) {
    fences.push(match.index);
  }

  // Check if we're inside an unclosed code fence
  const isInsideCodeFence = fences.length % 2 === 1;

  let completedContent: string;
  let pendingContent: string;

  if (isInsideCodeFence) {
    // Find the last opening fence
    const lastFenceStart = fences[fences.length - 1];
    // Everything before the unclosed fence is potentially complete
    const beforeFence = content.slice(0, lastFenceStart);
    const fenceAndAfter = content.slice(lastFenceStart);

    // Find the last complete block boundary before the fence
    const lastDoubleNewline = beforeFence.lastIndexOf('\n\n');
    if (lastDoubleNewline !== -1) {
      completedContent = beforeFence.slice(0, lastDoubleNewline);
      pendingContent = beforeFence.slice(lastDoubleNewline) + fenceAndAfter;
    } else {
      // No complete blocks before fence
      return { completedBlocks: [], pending: content };
    }
  } else {
    // Not inside a code fence - find the last double newline as block boundary
    const lastDoubleNewline = content.lastIndexOf('\n\n');
    if (lastDoubleNewline === -1) {
      // No double newline yet - everything is pending
      return { completedBlocks: [], pending: content };
    }

    // Content up to the last \n\n is complete
    completedContent = content.slice(0, lastDoubleNewline);
    // Content after the last \n\n is pending (may be empty if content ends with \n\n)
    pendingContent = content.slice(lastDoubleNewline + 2);
  }

  const completedBlocks = splitIntoBlocks(completedContent);
  return { completedBlocks, pending: pendingContent };
};

export interface MessageItemProps {
  message: UIMessage;
  isLastMessage: boolean;
  isLastAssistantMessage: boolean;
  isFirstConversationMessage: boolean;
  streamingMessageHeight: number | null;
  status: 'submitted' | 'streaming' | 'ready' | 'error';
  chatErrorType?: ChatErrorType;
  onRetry?: () => void;
  conversationId: string | undefined;
  isSourceOpen: string | null;
  isMobile: boolean;
  onCopyToClipboard: (content: string) => void;
  onOpenSources: (messageId: string) => void;
}

const MessageItemComponent: React.FC<MessageItemProps> = ({
  message,
  isLastMessage,
  isLastAssistantMessage,
  isFirstConversationMessage,
  streamingMessageHeight,
  status,
  chatErrorType,
  onRetry,
  conversationId,
  isSourceOpen,
  onCopyToClipboard,
  onOpenSources,
}) => {
  const { t } = useTranslation();
  const { data: config } = useConfig();
  const docsBaseUrl = config?.DOCS_BASE_URL;
  const contentRef = React.useRef<HTMLDivElement>(null);
  const [isCopied, setIsCopied] = React.useState(false);
  const copyTimeoutRef = React.useRef<number | null>(null);

  const showCopiedState = React.useCallback(() => {
    setIsCopied(true);
    if (copyTimeoutRef.current) {
      window.clearTimeout(copyTimeoutRef.current);
    }
    copyTimeoutRef.current = window.setTimeout(() => {
      setIsCopied(false);
      copyTimeoutRef.current = null;
    }, 3000);
  }, []);

  React.useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        window.clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const shouldApplyStreamingHeight =
    isLastAssistantMessage &&
    isLastMessage &&
    streamingMessageHeight &&
    !isFirstConversationMessage;

  const isCurrentlyStreaming =
    isLastAssistantMessage &&
    (status === 'streaming' || status === 'submitted');

  const co2ImpactKg = getMessageCo2Impact(message);

  const sourceParts = React.useMemo(
    () =>
      message.parts.filter(
        (part): part is SourceUrlUIPart => part.type === 'source-url',
      ),
    [message.parts],
  );

  const toolInvocationParts = React.useMemo(
    () => message.parts.filter(isToolUIPart),
    [message.parts],
  );

  const attachments = React.useMemo(
    () =>
      message.parts
        .filter((part) => part.type === 'file')
        .map((part) => ({
          name: part.filename,
          contentType: part.mediaType,
          url: part.url,
          skipped: (part as SkippableFileUIPart).skipped,
        })),
    [message.parts],
  );

  const textContent = React.useMemo(() => getMessageText(message), [message]);

  const hasTextContent = textContent.trim().length > 0;

  // v5 creates the assistant message as soon as the response starts, before any
  // content has arrived. That empty bubble must not carry the copy/feedback bar:
  // it put the thumbs up/down on screen ahead of the answer.
  const hasAssistantOutput =
    hasTextContent ||
    message.parts.some(
      (part) => part.type !== 'text' && part.type !== 'step-start',
    );

  const hasNonDocumentParsingTool = React.useMemo(
    () =>
      toolInvocationParts.some(
        (part) =>
          getToolName(part) !== 'document_parsing' &&
          getToolName(part) !== 'conversation_resume',
      ),
    [toolInvocationParts],
  );

  const activeToolInvocation = React.useMemo(
    () =>
      [...toolInvocationParts]
        .reverse()
        .find(
          (part) =>
            getToolName(part) !== 'document_parsing' &&
            part.state !== 'output-available' &&
            getToolName(part) !== 'conversation_resume',
        ),
    [toolInvocationParts],
  );

  const conversationSummarizeInvocation = React.useMemo(
    () =>
      [...toolInvocationParts]
        .reverse()
        .find(
          (part) =>
            getToolName(part) === 'summarize' &&
            (part.input as { summary_scope?: string })?.summary_scope ===
              'conversation',
        ),
    [toolInvocationParts],
  );

  // The summary phase failed the turn: the backend emits the `summarize`
  // tool-call before it can fail, so the invocation is still present here and
  // we render the failure (with a Retry) in the progress bar's slot.
  const summarizationFailed =
    isLastAssistantMessage &&
    status === 'error' &&
    chatErrorType === 'summarization_failed' &&
    !!conversationSummarizeInvocation;

  const [isSummarizationBarHidden, setIsSummarizationBarHidden] =
    React.useState(false);
  const handleSummarizationBarHidden = React.useCallback(
    () => setIsSummarizationBarHidden(true),
    [],
  );

  // Once the summary lands, the turn keeps streaming with an empty bubble until
  // the model emits its first answer token. Without this the progress bar just
  // vanishes and nothing replaces it, which reads as a stall.
  const showPostSummarizationLoader =
    isCurrentlyStreaming &&
    status === 'streaming' &&
    isSummarizationBarHidden &&
    !textContent &&
    !activeToolInvocation;

  // Memoize the streaming content split to avoid recreating components in JSX
  const { completedBlocks, pending } = React.useMemo(() => {
    // When not streaming, everything is completed as a single block array
    if (!isCurrentlyStreaming) {
      return {
        completedBlocks: splitIntoBlocks(textContent),
        pending: '',
      };
    }
    return splitStreamingContent(textContent);
  }, [isCurrentlyStreaming, textContent]);

  const handleCopy = React.useCallback(() => {
    const html = contentRef.current?.innerHTML;
    if (
      html &&
      typeof ClipboardItem !== 'undefined' &&
      navigator.clipboard.write
    ) {
      // Write both formats: Word/Docs use text/html (preserving formatting),
      // while code editors and plain-text apps use text/plain (raw markdown).
      const item = new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([textContent], { type: 'text/plain' }),
      });
      navigator.clipboard.write([item]).then(
        () => showCopiedState(),
        () => {
          onCopyToClipboard(textContent);
          showCopiedState();
        },
      );
    } else {
      onCopyToClipboard(textContent);
      showCopiedState();
    }
  }, [contentRef, textContent, onCopyToClipboard, showCopiedState]);

  const handleOpenSources = React.useCallback(() => {
    onOpenSources(message.id);
  }, [onOpenSources, message.id]);

  return (
    <Box
      data-message-id={message.id}
      data-testid={message.id}
      $css={`
        display: flex;
        width: 100%;
        margin: auto;
        margin-top: ${message.role === 'user' ? '32px' : '0px'};
        margin-bottom: ${isLastAssistantMessage || message.role === 'user' ? '32px' : '0px'};
        color: var(--c--theme--colors--greyscale-850);
        padding-left: 12px;
        padding-right: 12px;
        max-width: var(--chat-content-max-width, 750px);
        text-align: left;
        overflow-wrap: anywhere;
        flex-direction: ${message.role === 'user' ? 'row-reverse' : 'row'};
      `}
    >
      <Box
        $display="block"
        $width={`${message.role === 'user' ? 'auto' : '100%'}`}
      >
        {attachments.length > 0 && (
          <Box>
            <AttachmentList attachments={attachments} isReadOnly={true} />
          </Box>
        )}
        <Box
          className={`chatMessage ${message.role === 'user' ? 'chatMessage--user' : 'chatMessage--assistant'}`}
          style={
            shouldApplyStreamingHeight
              ? { minHeight: `${streamingMessageHeight}px` }
              : undefined
          }
        >
          {/* Message content */}
          {textContent && (
            <Box
              ref={contentRef}
              className="mainContent-chat"
              data-testid={
                message.role === 'assistant'
                  ? 'assistant-message-content'
                  : undefined
              }
            >
              <p className="sr-only">
                {message.role === 'user'
                  ? t('You said: ')
                  : t('Assistant IA replied: ')}
              </p>
              {message.role === 'user' ? (
                <Text
                  as="p"
                  $css="white-space: pre-wrap; display: block;"
                  $theme="greyscale"
                  $variation="850"
                >
                  {textContent}
                </Text>
              ) : (
                // Render completed blocks as markdown, pending block as plain text
                <BlocksList blocks={completedBlocks} pending={pending} />
              )}
            </Box>
          )}

          <Box $direction="column" $gap="2">
            {isCurrentlyStreaming &&
              isLastAssistantMessage &&
              status === 'streaming' &&
              conversationSummarizeInvocation && (
                <Box
                  $width="100%"
                  $maxWidth="var(--chat-content-max-width, 750px)"
                  $margin={{
                    all: 'auto',
                    top: 'base',
                    bottom: 'md',
                  }}
                >
                  <SummarizationProgress
                    done={
                      conversationSummarizeInvocation.state ===
                      'output-available'
                    }
                    onHidden={handleSummarizationBarHidden}
                  />
                </Box>
              )}
            {showPostSummarizationLoader && (
              <Box
                $direction="row"
                $align="center"
                $gap="6px"
                $width="100%"
                $maxWidth="var(--chat-content-max-width, 750px)"
                $margin={{
                  all: 'auto',
                  top: 'base',
                  bottom: 'md',
                }}
              >
                <Loader />
                <Text $variation="600" $size="md">
                  {t('Thinking...')}
                </Text>
              </Box>
            )}
            {summarizationFailed && onRetry && (
              <Box
                $width="100%"
                $maxWidth="var(--chat-content-max-width, 750px)"
                $margin={{
                  all: 'auto',
                  top: 'base',
                  bottom: 'md',
                }}
              >
                <SummarizationError onRetry={onRetry} />
              </Box>
            )}
            {isCurrentlyStreaming &&
              isLastAssistantMessage &&
              status === 'streaming' &&
              hasNonDocumentParsingTool &&
              activeToolInvocation &&
              activeToolInvocation !== conversationSummarizeInvocation && (
                <Box
                  $direction="row"
                  $align="center"
                  $gap="6px"
                  $width="100%"
                  $maxWidth="var(--chat-content-max-width, 750px)"
                  $margin={{
                    all: 'auto',
                    top: 'base',
                    bottom: 'md',
                  }}
                >
                  <Loader />
                  <Text $variation="600" $size="md">
                    {getToolName(activeToolInvocation) === 'summarize'
                      ? t('Summarizing...')
                      : t('Search...')}
                  </Text>
                </Box>
              )}
            {toolInvocationParts.map((part, partIndex) =>
              isLastAssistantMessage ? (
                <ToolInvocationItem
                  key={`tool-invocation-${partIndex}`}
                  toolInvocation={part}
                  status={status}
                  hideSearchLoader={true}
                />
              ) : null,
            )}
          </Box>

          {message.role === 'assistant' &&
            hasAssistantOutput &&
            !(isLastAssistantMessage && status === 'streaming') && (
              <Box
                $css="color: #222631; font-size: 12px;"
                $direction="row"
                $align="center"
                $justify="space-between"
                $gap="6px"
                $margin={{ top: 'base' }}
              >
                <Box $direction="row" $gap="4px">
                  <Button
                    size="nano"
                    color="neutral"
                    variant="tertiary"
                    onClick={handleCopy}
                    aria-label={isCopied ? t('Copied') : t('Copy')}
                    icon={
                      isCopied ? (
                        <CheckmarkIcon {...chatActionIconProps} />
                      ) : (
                        <ClipboardIcon {...chatActionIconProps} />
                      )
                    }
                    className="c__button--neutral action-chat-button"
                  ></Button>
                  {docsBaseUrl &&
                    conversationId &&
                    message.id &&
                    hasTextContent && (
                      <MoreActionsButton
                        conversationId={conversationId}
                        messageId={message.id}
                      />
                    )}
                  {sourceParts.length > 0 && (
                    <Button
                      size="nano"
                      variant="tertiary"
                      color="neutral"
                      onClick={handleOpenSources}
                      icon={<SourcesIcon {...chatActionIconProps} />}
                      className={`c__button--neutral action-chat-button ${
                        isSourceOpen === message.id
                          ? 'action-chat-button--open'
                          : ''
                      }`}
                    >
                      <Text $theme="neutral" $variation="tertiary">
                        {isSourceOpen !== message.id ? t('Show') : t('Hidden')}{' '}
                        {isSourceOpen !== message.id
                          ? `${sourceParts.length} `
                          : ''}
                        {sourceParts.length !== 1 ? t('sources') : t('source')}
                      </Text>
                    </Button>
                  )}
                </Box>
                <Box $direction="row" $gap="4px" $align="center">
                  {co2ImpactKg !== undefined && (
                    <MessageEnergyIndicator co2ImpactKg={co2ImpactKg} />
                  )}
                  {conversationId && message.id?.startsWith('trace-') && (
                    <FeedbackButtons
                      conversationId={conversationId}
                      messageId={message.id}
                    />
                  )}
                </Box>
              </Box>
            )}
        </Box>
      </Box>
    </Box>
  );
};

MessageItemComponent.displayName = 'MessageItem';

// Tool invocations advance through their states in place, without changing the
// parts count, so their states need their own signature: the summarization
// progress bar and the loader that replaces it hang on that transition.
const getToolInvocationStates = (message: UIMessage): string =>
  message.parts
    .filter(isToolUIPart)
    .map((part: ToolUIPart) => part.state)
    .join(',');

const getSourcePartsCount = (message: UIMessage): number =>
  message.parts.filter((part) => part.type === 'source-url').length;

const getFilePartsCount = (message: UIMessage): number =>
  message.parts.filter((part) => part.type === 'file').length;

// The backend can mark an image as skipped after the message was rendered, which
// only mutates the part in place - the part count stays the same.
const getSkippedFilePartsCount = (message: UIMessage): number =>
  message.parts.filter(
    (part) => part.type === 'file' && (part as SkippableFileUIPart).skipped,
  ).length;

// Custom comparison function for React.memo
// Only re-render when props that affect rendering change
const arePropsEqual = (
  prevProps: MessageItemProps,
  nextProps: MessageItemProps,
): boolean => {
  // Always re-render if message content changed
  if (prevProps.message.id !== nextProps.message.id) {
    return false;
  }
  if (getMessageText(prevProps.message) !== getMessageText(nextProps.message)) {
    return false;
  }
  if (prevProps.message.role !== nextProps.message.role) {
    return false;
  }

  if (
    getMessageCo2Impact(prevProps.message) !==
    getMessageCo2Impact(nextProps.message)
  ) {
    return false;
  }

  // Check parts changes (for streaming tool invocations and sources)
  const prevPartsLength = prevProps.message.parts.length;
  const nextPartsLength = nextProps.message.parts.length;
  if (prevPartsLength !== nextPartsLength) {
    return false;
  }
  if (
    getToolInvocationStates(prevProps.message) !==
    getToolInvocationStates(nextProps.message)
  ) {
    return false;
  }
  if (
    getSourcePartsCount(prevProps.message) !==
    getSourcePartsCount(nextProps.message)
  ) {
    return false;
  }

  // Check attachments
  if (
    getFilePartsCount(prevProps.message) !==
    getFilePartsCount(nextProps.message)
  ) {
    return false;
  }

  if (
    getSkippedFilePartsCount(prevProps.message) !==
    getSkippedFilePartsCount(nextProps.message)
  ) {
    return false;
  }

  // Check rendering flags
  if (prevProps.isLastMessage !== nextProps.isLastMessage) {
    return false;
  }
  if (prevProps.isLastAssistantMessage !== nextProps.isLastAssistantMessage) {
    return false;
  }
  if (
    prevProps.isFirstConversationMessage !==
    nextProps.isFirstConversationMessage
  ) {
    return false;
  }
  if (prevProps.streamingMessageHeight !== nextProps.streamingMessageHeight) {
    return false;
  }
  if (prevProps.status !== nextProps.status) {
    return false;
  }
  if (prevProps.chatErrorType !== nextProps.chatErrorType) {
    return false;
  }
  if (prevProps.onRetry !== nextProps.onRetry) {
    return false;
  }
  if (prevProps.isSourceOpen !== nextProps.isSourceOpen) {
    return false;
  }
  if (prevProps.isMobile !== nextProps.isMobile) {
    return false;
  }
  if (prevProps.conversationId !== nextProps.conversationId) {
    return false;
  }

  return true;
};

export const MessageItem = React.memo(MessageItemComponent, arePropsEqual);
