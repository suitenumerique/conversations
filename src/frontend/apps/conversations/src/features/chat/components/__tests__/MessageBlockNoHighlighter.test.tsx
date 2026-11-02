/* eslint-disable testing-library/no-unnecessary-act, @typescript-eslint/require-await */
import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { act, render, screen } from '@testing-library/react';
import { Suspense } from 'react';

import { CompletedMarkdownBlock } from '../MessageBlock';

// Kept apart from MessageBlock.test.tsx: MessageBlock starts loading the
// highlighter when the module is imported, so the failure has to be mocked for
// the whole file.

vi.mock('react-markdown', () => ({
  MarkdownHooks: ({ children }: { children: string }) => (
    <div data-testid="markdown-content">{children}</div>
  ),
}));

vi.mock('@shikijs/rehype/core', () => ({ default: () => {} }));
// What shiki's WASM engine does in a browser with WebAssembly disabled.
vi.mock('../../utils/shiki', () => ({
  getHighlighter: () =>
    Promise.reject(new ReferenceError('WebAssembly is not defined')),
}));
vi.mock('rehype-katex', () => ({ default: () => {} }));
vi.mock('remark-gfm', () => ({ default: () => {} }));
vi.mock('remark-math', () => ({ default: () => {} }));

describe('CompletedMarkdownBlock without a highlighter', () => {
  it('still renders the content', async () => {
    await act(async () => {
      render(
        <CunninghamProvider>
          <Suspense fallback={null}>
            <CompletedMarkdownBlock content="Hello world" />
          </Suspense>
        </CunninghamProvider>,
      );
    });

    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });
});
