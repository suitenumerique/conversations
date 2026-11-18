import { ReadableStream } from 'node:stream/web';
import { TextDecoder, TextEncoder } from 'node:util';
import { deserialize, serialize } from 'node:v8';

import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { Suspense, useEffect } from 'react';
import type { Mock } from 'vitest';

import { fetchAPI } from '@/api';
import { useChat } from '@/features/chat/api/useChat';
import { getMessageText } from '@/features/chat/utils/getMessageText';

import { CompletedMarkdownBlock } from '../MessageBlock';
import { splitStreamingContent } from '../MessageItem';

// react-markdown and the remark/rehype plugins stay real: the bug lives in how
// the markdown renderer commits. Only the shiki highlighter, which needs wasm,
// is stubbed.
vi.mock('@/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api')>()),
  fetchAPI: vi.fn(),
}));
vi.mock('@shikijs/rehype/core', () => ({ default: () => undefined }));
vi.mock('../../utils/shiki', () => ({
  getHighlighter: () => Promise.resolve({}),
}));

// jsdom ships none of the globals the SDK uses to read a streamed response.
Object.assign(globalThis, {
  ReadableStream,
  TextDecoder,
  TextEncoder,
  structuredClone: <T,>(value: T): T => deserialize(serialize(value)) as T,
});

// Well past React's limit of 50 nested updates, every delta closing a
// paragraph, all delivered in a single network read.
const PARAGRAPHS = 80;
const BURST = [
  'data: {"type":"start","messageId":"answer"}\n\n',
  'data: {"type":"text-start","id":"0"}\n\n',
  ...Array.from(
    { length: PARAGRAPHS },
    (_, i) =>
      `data: {"type":"text-delta","id":"0","delta":"Paragraph ${i}.\\n\\n"}\n\n`,
  ),
  'data: {"type":"text-end","id":"0"}\n\n',
  'data: {"type":"finish"}\n\n',
  'data: [DONE]\n\n',
].join('');

// Renders the streaming answer the way MessageItem does: one markdown block
// per completed paragraph.
const StreamedAnswer = ({ onError }: { onError: (error: Error) => void }) => {
  const { messages, sendMessage, status } = useChat({
    id: 'conv-1',
    api: 'chats/conv-1/conversation/',
    onError,
  });

  useEffect(() => {
    void sendMessage({ text: 'hello' });
  }, [sendMessage]);

  const answer = messages.findLast((message) => message.role === 'assistant');
  const { completedBlocks } = splitStreamingContent(
    answer ? getMessageText(answer) : '',
  );

  return (
    <>
      <div data-testid="status">{answer ? status : 'waiting'}</div>
      {completedBlocks.map((block, index) => (
        <CompletedMarkdownBlock key={index} content={block} />
      ))}
    </>
  );
};

describe('a burst of streamed paragraphs', () => {
  const actEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
    .IS_REACT_ACT_ENVIRONMENT;

  beforeEach(() => {
    // act() batches every update into one commit, which hides the bug: let
    // the stream drive React the way it does in the browser.
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = false;
    (vi.mocked(fetchAPI) as unknown as Mock).mockImplementation(
      (url: string) => {
        if (url.startsWith('chat-cooldown')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ cooldown_seconds: 0 }),
          });
        }
        return Promise.resolve({
          ok: true,
          body: new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(BURST));
              controller.close();
            },
          }),
        });
      },
    );
  });

  afterEach(() => {
    (
      globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = actEnvironment;
  });

  it('renders every paragraph without exceeding the update depth', async () => {
    const onError = vi.fn();

    render(
      <QueryClientProvider client={new QueryClient()}>
        <CunninghamProvider>
          <Suspense fallback={null}>
            <StreamedAnswer onError={onError} />
          </Suspense>
        </CunninghamProvider>
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent(/ready|error/),
    );

    expect(onError).not.toHaveBeenCalled();
    expect(screen.getByTestId('status')).toHaveTextContent('ready');
    expect(
      await screen.findByText(`Paragraph ${PARAGRAPHS - 1}.`),
    ).toBeInTheDocument();
  });
});
