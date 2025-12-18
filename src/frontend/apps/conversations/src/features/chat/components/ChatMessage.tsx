import {
  Message,
  ReasoningUIPart,
  SourceUIPart,
  ToolInvocationUIPart,
} from '@ai-sdk/ui-utils';
import 'katex/dist/katex.min.css';
import { memo, useDeferredValue } from 'react';
import { useTranslation } from 'react-i18next';
import { MarkdownHooks } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import rehypePrettyCode from 'rehype-pretty-code';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

import { Box, Icon, Text } from '@/components';
import { useClipboard } from '@/hook';
import { useResponsiveStore } from '@/stores';

import { AttachmentList } from './AttachmentList';
import { CodeBlock } from './CodeBlock';
import { FeedbackButtons } from './FeedbackButtons';
import { SourceItemList } from './SourceItemList';
import { ToolInvocationItem } from './ToolInvocationItem';

// Mémoriser les plugins Markdown en dehors du composant pour éviter les recréations
const remarkPlugins = [remarkGfm, remarkMath];
const rehypePlugins = [
  [
    rehypePrettyCode,
    {
      theme: 'github-dark-dimmed',
    },
  ],
  rehypeKatex,
];

// Composants Markdown mémorisés
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const markdownComponents: any = {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars, @typescript-eslint/no-explicit-any
  p: ({ node, ...props }: any) => (
    <Text
      as="p"
      $css="display: block"
      $theme="greyscale"
      $variation="850"
      {...props}
    />
  ),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  a: ({ children, ...props }: any) => (
    <a target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  ),
  // eslint-disable-next-line @typescript-eslint/no-unused-vars, @typescript-eslint/no-explicit-any
  pre: ({ node, children, ...props }: any) => (
    <CodeBlock {...props}>{children}</CodeBlock>
  ),
};

// Composant Markdown mémorisé pour éviter les recalculs inutiles
const MemoizedMarkdown = memo(function MemoizedMarkdown({
  content,
}: {
  content: string;
}) {
  return (
    <MarkdownHooks
      remarkPlugins={remarkPlugins}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-assignment
      rehypePlugins={rehypePlugins as any} // Type mismatch with react-markdown types
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      components={markdownComponents}
    >
      {content}
    </MarkdownHooks>
  );
});

interface ChatMessageProps {
  message: Message;
  isLastAssistantMessageInConversation: boolean;
  shouldApplyStreamingHeight: boolean;
  streamingMessageHeight: number | null;
  isCurrentlyStreaming: boolean;
  status: 'idle' | 'streaming' | 'submitted' | 'ready' | 'error';
  isSourceOpen: string | null;
  conversationId: string | undefined;
  onOpenSources: (messageId: string) => void;
  getMetadata: (url: string) =>
    | {
        title: string | null;
        favicon: string | null;
        loading: boolean;
        error: boolean;
      }
    | undefined;
}

export const ChatMessage = memo(function ChatMessage({
  message,
  isLastAssistantMessageInConversation,
  shouldApplyStreamingHeight,
  streamingMessageHeight,
  isCurrentlyStreaming,
  status,
  isSourceOpen,
  conversationId,
  onOpenSources,
  getMetadata,
}: ChatMessageProps) {
  const { t } = useTranslation();
  const copyToClipboard = useClipboard();
  const { isMobile } = useResponsiveStore();

  const deferredContent = useDeferredValue(message.content);

  const contentToRender =
    message.role === 'assistant' ? deferredContent : message.content;

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
            ${shouldApplyStreamingHeight ? `min-height: ${streamingMessageHeight}px;` : ''}
          `}
        >
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
                <MemoizedMarkdown content={contentToRender} />
              )}
            </Box>
          )}

          <Box $direction="column" $gap="2">
            {isCurrentlyStreaming &&
              isLastAssistantMessageInConversation &&
              status === 'streaming' &&
              message.parts?.some(
                (part) =>
                  part.type === 'tool-invocation' &&
                  part.toolInvocation.toolName !== 'document_parsing',
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
                  <Text $variation="600" $size="md">
                    {(() => {
                      const toolInvocation = message.parts?.find(
                        (part) =>
                          part.type === 'tool-invocation' &&
                          part.toolInvocation.toolName !== 'document_parsing',
                      );
                      if (
                        toolInvocation?.type === 'tool-invocation' &&
                        toolInvocation.toolInvocation.toolName === 'summarize'
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
                  part.type === 'reasoning' || part.type === 'tool-invocation',
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
              isLastAssistantMessageInConversation && status === 'streaming'
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
                  {message.parts?.some((part) => part.type === 'source') &&
                    (() => {
                      const sourceCount =
                        message.parts?.filter((part) => part.type === 'source')
                          .length || 0;
                      return (
                        <Box
                          $direction="row"
                          $align="center"
                          $gap="4px"
                          className={`c__button--neutral action-chat-button ${isSourceOpen === message.id ? 'action-chat-button--open' : ''}`}
                          onClick={() => onOpenSources(message.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              onOpenSources(message.id);
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
                            {sourceCount !== 1 ? t('sources') : t('source')}
                          </Text>
                        </Box>
                      );
                    })()}
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
          {message.parts &&
            isSourceOpen === message.id &&
            (() => {
              const sourceParts = message.parts.filter(
                (part): part is SourceUIPart => part.type === 'source',
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
});
