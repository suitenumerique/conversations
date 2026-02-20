import { Message, SourceUIPart, ToolInvocationUIPart } from '@ai-sdk/ui-utils';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Loader, Text } from '@/components';
import { AttachmentList } from '@/features/chat/components/AttachmentList';
import { FeedbackButtons } from '@/features/chat/components/FeedbackButtons';
import {
  CompletedMarkdownBlock,
  RawTextBlock,
} from '@/features/chat/components/MessageBlock';
import { SourceItemList } from '@/features/chat/components/SourceItemList';
import { ToolInvocationItem } from '@/features/chat/components/ToolInvocationItem';

// Memoized blocks list to prevent parent re-renders from causing block remounts
const BlocksList = React.memo(
  ({ blocks, pending }: { blocks: string[]; pending: string }) => (
    <div>
      {/* key={index} is safe here: blocks are append-only during streaming
         and a completed block's content never changes once finalized. */}
      {blocks.map((block, index) => (
        <CompletedMarkdownBlock key={index} content={block} />
      ))}
      {pending && <RawTextBlock content={pending} />}
    </div>
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

interface SourceMetadata {
  title: string | null;
  favicon: string | null;
  loading: boolean;
  error: boolean;
}

export interface MessageItemProps {
  message: Message;
  isLastMessage: boolean;
  isLastAssistantMessage: boolean;
  isFirstConversationMessage: boolean;
  streamingMessageHeight: number | null;
  status: 'submitted' | 'streaming' | 'ready' | 'error';
  conversationId: string | undefined;
  isSourceOpen: string | null;
  isMobile: boolean;
  onCopyToClipboard: (content: string) => void;
  onOpenSources: (messageId: string) => void;
  getMetadata: (url: string) => SourceMetadata | undefined;
}

const MessageItemComponent: React.FC<MessageItemProps> = ({
  message,
  isLastMessage,
  isLastAssistantMessage,
  isFirstConversationMessage,
  streamingMessageHeight,
  status,
  conversationId,
  isSourceOpen,
  isMobile,
  onCopyToClipboard,
  onOpenSources,
  getMetadata,
}) => {
  const { t } = useTranslation();

  const shouldApplyStreamingHeight =
    isLastAssistantMessage &&
    isLastMessage &&
    streamingMessageHeight &&
    !isFirstConversationMessage;

  const isCurrentlyStreaming =
    isLastAssistantMessage &&
    (status === 'streaming' || status === 'submitted');

  const sourceParts = React.useMemo(() => {
    if (!message.parts) {
      return [];
    }
    return message.parts.filter(
      (part): part is SourceUIPart => part.type === 'source',
    );
  }, [message.parts]);

  const toolInvocationParts = React.useMemo(() => {
    if (!message.parts) {
      return [];
    }
    return message.parts.filter(
      (part): part is ToolInvocationUIPart => part.type === 'tool-invocation',
    );
  }, [message.parts]);

  const hasNonDocumentParsingTool = React.useMemo(() => {
    return toolInvocationParts.some(
      (part) => part.toolInvocation.toolName !== 'document_parsing',
    );
  }, [toolInvocationParts]);

  const activeToolInvocation = React.useMemo(() => {
    const tool = toolInvocationParts.find(
      (part) => part.toolInvocation.toolName !== 'document_parsing',
    );
    return tool?.toolInvocation;
  }, [toolInvocationParts]);

  const activeToolInvocationDisplayName = React.useMemo(() => {
    if (!activeToolInvocation) {
      return '';
    }

    if (activeToolInvocation.toolName === 'summarize') {
      return t('Summarizing...');
    }
    if (activeToolInvocation.toolName === 'translate') {
      return t('Translation in progress...');
    }

    return t('Search...');
  }, [activeToolInvocation, t]);

  // Memoize the streaming content split to avoid recreating components in JSX
  const { completedBlocks, pending } = React.useMemo(() => {
    // When not streaming, everything is completed as a single block array
    if (!isCurrentlyStreaming) {
      return {
        completedBlocks: splitIntoBlocks(message.content),
        pending: '',
      };
    }
    return splitStreamingContent(message.content);
  }, [isCurrentlyStreaming, message.content]);

  const handleCopy = React.useCallback(() => {
    onCopyToClipboard(message.content);
  }, [onCopyToClipboard, message.content]);

  const handleCopyKeyDown = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onCopyToClipboard(message.content);
      }
    },
    [onCopyToClipboard, message.content],
  );

  const handleOpenSources = React.useCallback(() => {
    onOpenSources(message.id);
  }, [onOpenSources, message.id]);

  const handleOpenSourcesKeyDown = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onOpenSources(message.id);
      }
    },
    [onOpenSources, message.id],
  );

  return (
    <Box
      data-message-id={message.id}
      data-testid={message.id}
      $css={`
        display: flex;
        width: 100%;
        margin: auto;
        margin-bottom: ${isLastAssistantMessage ? '30px' : '0px'};
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
              data-testid={
                message.role === 'assistant'
                  ? 'assistant-message-content'
                  : undefined
              }
              $padding={{ all: 'xxs' }}
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
                  {message.content}
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
              hasNonDocumentParsingTool && (
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
                    {activeToolInvocationDisplayName}
                  </Text>
                </Box>
              )}
            {toolInvocationParts.map((part, partIndex) =>
              isCurrentlyStreaming && isLastAssistantMessage ? (
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
                  <Box
                    $direction="row"
                    $align="center"
                    $gap="4px"
                    className="c__button--neutral action-chat-button"
                    onClick={handleCopy}
                    onKeyDown={handleCopyKeyDown}
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
                  {sourceParts.length > 0 && (
                    <Box
                      $direction="row"
                      $align="center"
                      $gap="4px"
                      className={`c__button--neutral action-chat-button ${isSourceOpen === message.id ? 'action-chat-button--open' : ''}`}
                      onClick={handleOpenSources}
                      onKeyDown={handleOpenSourcesKeyDown}
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
                        {t('Show')} {sourceParts.length}{' '}
                        {sourceParts.length !== 1 ? t('sources') : t('source')}
                      </Text>
                    </Box>
                  )}
                </Box>
                <Box $direction="row" $gap="4px">
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

          {isSourceOpen === message.id && sourceParts.length > 0 && (
            <Box
              $css={`
                animation: fade-in 0.2s ease-out;
              `}
            >
              <SourceItemList parts={sourceParts} getMetadata={getMetadata} />
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
};

MessageItemComponent.displayName = 'MessageItem';

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
  if (prevProps.message.content !== nextProps.message.content) {
    return false;
  }
  if (prevProps.message.role !== nextProps.message.role) {
    return false;
  }

  // Check parts changes (for streaming tool invocations and sources)
  const prevPartsLength = prevProps.message.parts?.length ?? 0;
  const nextPartsLength = nextProps.message.parts?.length ?? 0;
  if (prevPartsLength !== nextPartsLength) {
    return false;
  }

  // Check attachments
  const prevAttachmentsLength =
    prevProps.message.experimental_attachments?.length ?? 0;
  const nextAttachmentsLength =
    nextProps.message.experimental_attachments?.length ?? 0;
  if (prevAttachmentsLength !== nextAttachmentsLength) {
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
