/* eslint-disable testing-library/no-unnecessary-act, @typescript-eslint/require-await */
import { CunninghamProvider } from '@openfun/cunningham-react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Suspense } from 'react';

import {
  MessageItem,
  splitIntoBlocks,
  splitStreamingContent,
} from '../MessageItem';

// Mock react-markdown (ESM module)
jest.mock('react-markdown', () => ({
  MarkdownHooks: ({ children }: { children: string }) => (
    <div data-testid="markdown-content">{children}</div>
  ),
}));

jest.mock('@shikijs/rehype/core', () => () => {});
jest.mock('../../utils/shiki', () => ({
  getHighlighter: () => Promise.resolve({}),
}));
jest.mock('rehype-katex', () => () => {});
jest.mock('remark-gfm', () => () => {});
jest.mock('remark-math', () => () => {});

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock child components
jest.mock('../AttachmentList', () => ({
  AttachmentList: () => <div data-testid="attachment-list" />,
}));

jest.mock('../FeedbackButtons', () => ({
  FeedbackButtons: () => <div data-testid="feedback-buttons" />,
}));

jest.mock('../SourceItemList', () => ({
  SourceItemList: () => <div data-testid="source-item-list" />,
}));

jest.mock('../ToolInvocationItem', () => ({
  ToolInvocationItem: () => <div data-testid="tool-invocation-item" />,
}));

describe('splitIntoBlocks', () => {
  describe('basic splitting', () => {
    it('returns empty array for empty content', () => {
      expect(splitIntoBlocks('')).toEqual([]);
    });

    it('returns empty array for null/undefined content', () => {
      expect(splitIntoBlocks(null as unknown as string)).toEqual([]);
      expect(splitIntoBlocks(undefined as unknown as string)).toEqual([]);
    });

    it('returns single block for content without double newlines', () => {
      expect(splitIntoBlocks('Hello world')).toEqual(['Hello world']);
    });

    it('splits content by double newlines', () => {
      expect(splitIntoBlocks('Block 1\n\nBlock 2')).toEqual([
        'Block 1',
        'Block 2',
      ]);
    });

    it('splits multiple blocks', () => {
      expect(splitIntoBlocks('Block 1\n\nBlock 2\n\nBlock 3')).toEqual([
        'Block 1',
        'Block 2',
        'Block 3',
      ]);
    });

    it('ignores single newlines', () => {
      expect(splitIntoBlocks('Line 1\nLine 2\n\nBlock 2')).toEqual([
        'Line 1\nLine 2',
        'Block 2',
      ]);
    });

    it('filters out empty blocks', () => {
      expect(splitIntoBlocks('Block 1\n\n\n\nBlock 2')).toEqual([
        'Block 1',
        'Block 2',
      ]);
    });

    it('filters out whitespace-only blocks', () => {
      expect(splitIntoBlocks('Block 1\n\n   \n\nBlock 2')).toEqual([
        'Block 1',
        'Block 2',
      ]);
    });
  });

  describe('code fence handling', () => {
    it('keeps code block with internal double newlines as single block', () => {
      const content = '```python\nline1\n\nline2\n```';
      expect(splitIntoBlocks(content)).toEqual([content]);
    });

    it('keeps code block intact when followed by other content', () => {
      const content = '```python\ncode\n```\n\nText after';
      expect(splitIntoBlocks(content)).toEqual([
        '```python\ncode\n```',
        'Text after',
      ]);
    });

    it('keeps code block intact when preceded by other content', () => {
      const content = 'Text before\n\n```python\ncode\n```';
      expect(splitIntoBlocks(content)).toEqual([
        'Text before',
        '```python\ncode\n```',
      ]);
    });

    it('handles multiple code blocks', () => {
      const content = '```js\ncode1\n```\n\nText\n\n```python\ncode2\n```';
      expect(splitIntoBlocks(content)).toEqual([
        '```js\ncode1\n```',
        'Text',
        '```python\ncode2\n```',
      ]);
    });

    it('handles code block with multiple double newlines inside', () => {
      const content = '```\nline1\n\nline2\n\nline3\n```';
      expect(splitIntoBlocks(content)).toEqual([content]);
    });

    it('handles nested backticks inside code block', () => {
      const content = '```markdown\nSome `inline` code\n\nMore text\n```';
      expect(splitIntoBlocks(content)).toEqual([content]);
    });

    it('handles unclosed code fence', () => {
      const content = 'Text\n\n```python\ncode without closing';
      const result = splitIntoBlocks(content);
      // The unclosed fence should be kept with the text before it
      expect(result).toEqual(['Text', '```python\ncode without closing']);
    });
  });

  describe('edge cases', () => {
    it('handles content ending with double newline', () => {
      expect(splitIntoBlocks('Block 1\n\nBlock 2\n\n')).toEqual([
        'Block 1',
        'Block 2',
      ]);
    });

    it('handles content starting with double newline', () => {
      expect(splitIntoBlocks('\n\nBlock 1\n\nBlock 2')).toEqual([
        'Block 1',
        'Block 2',
      ]);
    });

    it('handles markdown headers', () => {
      expect(splitIntoBlocks('# Header\n\nParagraph')).toEqual([
        '# Header',
        'Paragraph',
      ]);
    });

    it('handles markdown lists', () => {
      const content = '- Item 1\n- Item 2\n\nParagraph';
      expect(splitIntoBlocks(content)).toEqual([
        '- Item 1\n- Item 2',
        'Paragraph',
      ]);
    });
  });
});

describe('splitStreamingContent', () => {
  describe('basic splitting', () => {
    it('returns empty blocks and empty pending for empty content', () => {
      expect(splitStreamingContent('')).toEqual({
        completedBlocks: [],
        pending: '',
      });
    });

    it('returns all content as pending when no double newline', () => {
      expect(splitStreamingContent('Partial content')).toEqual({
        completedBlocks: [],
        pending: 'Partial content',
      });
    });

    it('splits completed and pending content', () => {
      expect(splitStreamingContent('Block 1\n\nPending')).toEqual({
        completedBlocks: ['Block 1'],
        pending: 'Pending',
      });
    });

    it('handles multiple completed blocks with pending', () => {
      expect(splitStreamingContent('Block 1\n\nBlock 2\n\nPending')).toEqual({
        completedBlocks: ['Block 1', 'Block 2'],
        pending: 'Pending',
      });
    });
  });

  describe('content ending with double newline (bug fix)', () => {
    it('keeps blocks when content ends with double newline', () => {
      // This was the bug: content ending with \n\n would return empty blocks
      const result = splitStreamingContent('Block 1\n\nBlock 2\n\n');
      expect(result.completedBlocks).toEqual(['Block 1', 'Block 2']);
      expect(result.pending).toBe('');
    });

    it('keeps single block when content ends with double newline', () => {
      const result = splitStreamingContent('Block 1\n\n');
      expect(result.completedBlocks).toEqual(['Block 1']);
      expect(result.pending).toBe('');
    });

    it('handles multiple trailing double newlines', () => {
      // 'Block 1\n\n\n\n' - lastIndexOf('\n\n') finds the last pair
      // completedContent = 'Block 1\n\n', pending = ''
      const result = splitStreamingContent('Block 1\n\n\n\n');
      expect(result.completedBlocks).toEqual(['Block 1']);
      expect(result.pending).toBe('');
    });
  });

  describe('code fence handling', () => {
    it('treats unclosed code fence as pending', () => {
      const result = splitStreamingContent('Text\n\n```python\ncode');
      expect(result.completedBlocks).toEqual(['Text']);
      expect(result.pending).toBe('\n\n```python\ncode');
    });

    it('handles closed code fence as completed', () => {
      const result = splitStreamingContent('```python\ncode\n```\n\nPending');
      expect(result.completedBlocks).toEqual(['```python\ncode\n```']);
      expect(result.pending).toBe('Pending');
    });

    it('handles unclosed fence with no content before', () => {
      const result = splitStreamingContent('```python\ncode');
      expect(result.completedBlocks).toEqual([]);
      expect(result.pending).toBe('```python\ncode');
    });

    it('handles unclosed fence with double newline inside', () => {
      const result = splitStreamingContent('Text\n\n```python\nline1\n\nline2');
      expect(result.completedBlocks).toEqual(['Text']);
      expect(result.pending).toContain('```python');
    });

    it('handles multiple code blocks', () => {
      const result = splitStreamingContent(
        '```js\ncode1\n```\n\n```python\ncode2\n```\n\nPending',
      );
      expect(result.completedBlocks).toEqual([
        '```js\ncode1\n```',
        '```python\ncode2\n```',
      ]);
      expect(result.pending).toBe('Pending');
    });
  });

  describe('streaming simulation', () => {
    it('maintains block stability as content grows', () => {
      // Simulate streaming: content grows over time
      const stream1 = 'Hello';
      const stream2 = 'Hello world';
      const stream3 = 'Hello world\n\n';
      const stream4 = 'Hello world\n\nSecond';
      const stream5 = 'Hello world\n\nSecond block\n\n';
      const stream6 = 'Hello world\n\nSecond block\n\nThird';

      // Initially all pending
      expect(splitStreamingContent(stream1).completedBlocks).toEqual([]);
      expect(splitStreamingContent(stream2).completedBlocks).toEqual([]);

      // After first \n\n, first block is complete
      const result3 = splitStreamingContent(stream3);
      expect(result3.completedBlocks).toEqual(['Hello world']);
      expect(result3.pending).toBe('');

      // New content arrives
      const result4 = splitStreamingContent(stream4);
      expect(result4.completedBlocks).toEqual(['Hello world']);
      expect(result4.pending).toBe('Second');

      // Second block completes
      const result5 = splitStreamingContent(stream5);
      expect(result5.completedBlocks).toEqual(['Hello world', 'Second block']);
      expect(result5.pending).toBe('');

      // More content
      const result6 = splitStreamingContent(stream6);
      expect(result6.completedBlocks).toEqual(['Hello world', 'Second block']);
      expect(result6.pending).toBe('Third');
    });

    it('block content remains stable during streaming', () => {
      // The key test: first block content should not change as more content arrives
      const stream1 = 'First block\n\nSecond';
      const stream2 = 'First block\n\nSecond block\n\nThird';

      const result1 = splitStreamingContent(stream1);
      const result2 = splitStreamingContent(stream2);

      // First block should be identical
      expect(result1.completedBlocks[0]).toBe(result2.completedBlocks[0]);
      expect(result1.completedBlocks[0]).toBe('First block');
    });
  });

  describe('edge cases', () => {
    it('handles only whitespace', () => {
      expect(splitStreamingContent('   ')).toEqual({
        completedBlocks: [],
        pending: '   ',
      });
    });

    it('handles only newlines', () => {
      expect(splitStreamingContent('\n\n')).toEqual({
        completedBlocks: [],
        pending: '',
      });
    });

    it('handles special characters', () => {
      const result = splitStreamingContent('Special: < > & "\n\nMore');
      expect(result.completedBlocks).toEqual(['Special: < > & "']);
      expect(result.pending).toBe('More');
    });
  });
});

describe('MessageItem', () => {
  const defaultProps = {
    message: {
      id: 'msg-1',
      role: 'assistant' as const,
      content: 'Hello world',
    },
    isLastMessage: false,
    isLastAssistantMessage: false,
    isFirstConversationMessage: false,
    streamingMessageHeight: null,
    status: 'ready' as const,
    conversationId: 'conv-1',
    isSourceOpen: null,
    isMobile: false,
    onCopyToClipboard: jest.fn(),
    onOpenSources: jest.fn(),
    getMetadata: jest.fn(),
  };

  const renderWithProviders = (ui: React.ReactNode) => {
    return render(
      <CunninghamProvider>
        <Suspense fallback={null}>{ui}</Suspense>
      </CunninghamProvider>,
    );
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders assistant message content', async () => {
      await act(async () => {
        renderWithProviders(<MessageItem {...defaultProps} />);
      });

      expect(
        screen.getByTestId('assistant-message-content'),
      ).toBeInTheDocument();
    });

    it('renders user message content', async () => {
      await act(async () => {
        renderWithProviders(
          <MessageItem
            {...defaultProps}
            message={{ ...defaultProps.message, role: 'user' }}
          />,
        );
      });

      expect(screen.getByText('Hello world')).toBeInTheDocument();
    });

    it('renders message with data-message-id attribute', async () => {
      await act(async () => {
        renderWithProviders(<MessageItem {...defaultProps} />);
      });

      expect(screen.getByTestId('msg-1')).toBeInTheDocument();
    });

    it('renders copy button for non-streaming assistant messages', async () => {
      await act(async () => {
        renderWithProviders(<MessageItem {...defaultProps} />);
      });

      expect(screen.getByText('Copy')).toBeInTheDocument();
    });

    it('does not render copy button while streaming', async () => {
      await act(async () => {
        renderWithProviders(
          <MessageItem
            {...defaultProps}
            status="streaming"
            isLastAssistantMessage={true}
          />,
        );
      });

      expect(screen.queryByText('Copy')).not.toBeInTheDocument();
    });

    it('hides copy text on mobile', async () => {
      await act(async () => {
        renderWithProviders(<MessageItem {...defaultProps} isMobile={true} />);
      });

      expect(screen.queryByText('Copy')).not.toBeInTheDocument();
    });
  });

  describe('interactions', () => {
    it('calls onCopyToClipboard when copy button is clicked', async () => {
      const user = userEvent.setup();
      const onCopyToClipboard = jest.fn();

      await act(async () => {
        renderWithProviders(
          <MessageItem
            {...defaultProps}
            onCopyToClipboard={onCopyToClipboard}
          />,
        );
      });

      await user.click(screen.getByText('Copy'));

      expect(onCopyToClipboard).toHaveBeenCalledWith('Hello world');
    });
  });

  describe('streaming state', () => {
    it('uses splitStreamingContent when streaming', async () => {
      // When streaming, content should be split into blocks + pending
      await act(async () => {
        renderWithProviders(
          <MessageItem
            {...defaultProps}
            message={{
              ...defaultProps.message,
              content: 'Block 1\n\nPending content',
            }}
            status="streaming"
            isLastAssistantMessage={true}
          />,
        );
      });

      // The markdown content should contain "Block 1" but not necessarily "Pending"
      // since pending is rendered as raw text
      expect(
        screen.getByTestId('assistant-message-content'),
      ).toBeInTheDocument();
    });
  });

  describe('attachments', () => {
    it('renders AttachmentList when message has attachments', async () => {
      const messageWithAttachments = {
        ...defaultProps.message,
        experimental_attachments: [
          { url: 'https://example.com/file.pdf', name: 'file.pdf' },
        ],
      };

      await act(async () => {
        renderWithProviders(
          <MessageItem {...defaultProps} message={messageWithAttachments} />,
        );
      });

      expect(screen.getByTestId('attachment-list')).toBeInTheDocument();
    });

    it('does not render AttachmentList when no attachments', async () => {
      await act(async () => {
        renderWithProviders(<MessageItem {...defaultProps} />);
      });

      expect(screen.queryByTestId('attachment-list')).not.toBeInTheDocument();
    });
  });

  describe('feedback buttons', () => {
    it('renders FeedbackButtons for trace messages', async () => {
      await act(async () => {
        renderWithProviders(
          <MessageItem
            {...defaultProps}
            message={{ ...defaultProps.message, id: 'trace-123' }}
          />,
        );
      });

      expect(screen.getByTestId('feedback-buttons')).toBeInTheDocument();
    });

    it('does not render FeedbackButtons for non-trace messages', async () => {
      await act(async () => {
        renderWithProviders(<MessageItem {...defaultProps} />);
      });

      expect(screen.queryByTestId('feedback-buttons')).not.toBeInTheDocument();
    });
  });
});
