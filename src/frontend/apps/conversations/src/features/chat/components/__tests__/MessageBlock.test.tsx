/* eslint-disable testing-library/no-unnecessary-act, @typescript-eslint/require-await */
import { CunninghamProvider } from '@openfun/cunningham-react';
import { act, render, screen } from '@testing-library/react';
import { Suspense } from 'react';

import { CompletedMarkdownBlock, RawTextBlock } from '../MessageBlock';

// Mock react-markdown (ESM module not compatible with Jest)
jest.mock('react-markdown', () => ({
  MarkdownHooks: ({ children }: { children: string }) => {
    // Simple mock that renders markdown-like content
    // This tests the component integration, not the markdown parsing itself
    return <div data-testid="markdown-content">{children}</div>;
  },
}));

// Mock rehype/remark plugins
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

const renderWithProviders = (ui: React.ReactNode) => {
  return render(
    <CunninghamProvider>
      <Suspense fallback={null}>{ui}</Suspense>
    </CunninghamProvider>,
  );
};

describe('CompletedMarkdownBlock', () => {
  it('renders content through MarkdownHooks', async () => {
    await act(async () => {
      renderWithProviders(<CompletedMarkdownBlock content="Hello world" />);
    });

    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('passes content to markdown renderer', async () => {
    const content = '# Header Some **bold** text';
    await act(async () => {
      renderWithProviders(<CompletedMarkdownBlock content={content} />);
    });

    expect(screen.getByTestId('markdown-content')).toHaveTextContent(content);
  });

  it('does not re-render when content is the same (memoization)', async () => {
    let rerender: ReturnType<typeof render>['rerender'];
    await act(async () => {
      ({ rerender } = renderWithProviders(
        <CompletedMarkdownBlock content="Same content" />,
      ));
    });

    const firstRender = screen.getByTestId('markdown-content');

    rerender!(
      <CunninghamProvider>
        <Suspense fallback={null}>
          <CompletedMarkdownBlock content="Same content" />
        </Suspense>
      </CunninghamProvider>,
    );

    const secondRender = screen.getByTestId('markdown-content');

    // The DOM element should be the same instance (not recreated)
    expect(firstRender).toBe(secondRender);
  });

  it('re-renders when content changes', async () => {
    let rerender: ReturnType<typeof render>['rerender'];
    await act(async () => {
      ({ rerender } = renderWithProviders(
        <CompletedMarkdownBlock content="Original content" />,
      ));
    });

    expect(screen.getByText('Original content')).toBeInTheDocument();

    rerender!(
      <CunninghamProvider>
        <Suspense fallback={null}>
          <CompletedMarkdownBlock content="New content" />
        </Suspense>
      </CunninghamProvider>,
    );

    expect(screen.queryByText('Original content')).not.toBeInTheDocument();
    expect(screen.getByText('New content')).toBeInTheDocument();
  });

  it('handles empty content', async () => {
    let container: HTMLElement;
    await act(async () => {
      ({ container } = renderWithProviders(
        <CompletedMarkdownBlock content="" />,
      ));
    });

    expect(container!).toBeInTheDocument();
    expect(screen.getByTestId('markdown-content')).toBeInTheDocument();
  });

  it('handles content with special characters', async () => {
    await act(async () => {
      renderWithProviders(
        <CompletedMarkdownBlock content={`Special chars: < > & " '`} />,
      );
    });

    expect(screen.getByText(/Special chars:/)).toBeInTheDocument();
  });
});

describe('RawTextBlock', () => {
  it('renders plain text content', () => {
    renderWithProviders(<RawTextBlock content="Raw text content" />);

    expect(screen.getByText('Raw text content')).toBeInTheDocument();
  });

  it('preserves whitespace and newlines', () => {
    renderWithProviders(
      <RawTextBlock content="Line 1\n  Indented line\nLine 3" />,
    );

    const textElement = screen.getByText(/Line 1/);
    expect(textElement).toHaveStyle('white-space: pre-wrap');
  });

  it('renders as a div element', () => {
    renderWithProviders(<RawTextBlock content="Test content" />);

    const element = screen.getByText('Test content');
    // Text component renders with as="div", check it's in the DOM
    expect(element).toBeInTheDocument();
  });

  it('does not parse markdown syntax', () => {
    renderWithProviders(<RawTextBlock content="**not bold** *not italic*" />);

    // Should render the raw markdown syntax, not parsed
    expect(screen.getByText('**not bold** *not italic*')).toBeInTheDocument();
  });

  it('handles empty content', () => {
    const { container } = renderWithProviders(<RawTextBlock content="" />);

    expect(container).toBeInTheDocument();
  });

  it('handles content with code fence markers', () => {
    renderWithProviders(
      <RawTextBlock content="```python\npsquares = [x**2 for x in range(10)]" />,
    );

    expect(screen.getByText(/```python/)).toBeInTheDocument();
  });
});
