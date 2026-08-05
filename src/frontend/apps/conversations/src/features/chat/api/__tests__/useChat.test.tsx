import { ReadableStream } from 'node:stream/web';
import { TextDecoder, TextEncoder } from 'node:util';
import { deserialize, serialize } from 'node:v8';

import { Message } from '@ai-sdk/ui-utils';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';

import {
  isImagesSkippedEvent,
  stampImagesSkippedOnLatestUserMessage,
  useChat,
} from '../useChat';

jest.mock('@/api', () => ({
  fetchAPI: jest.fn(),
}));

describe('isImagesSkippedEvent', () => {
  it('accepts a chat_notice event', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        kind: 'chat_notice',
        reason: 'model_text_only',
      }),
    ).toBe(true);
  });

  it('accepts a last_message_marked event', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        kind: 'last_message_marked',
        reason: 'model_text_only',
      }),
    ).toBe(true);
  });

  it('rejects events of other types', () => {
    expect(isImagesSkippedEvent({ type: 'some_other_event' })).toBe(false);
  });

  it('rejects events with unknown kind', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        kind: 'something-else',
        reason: 'model_text_only',
      }),
    ).toBe(false);
  });

  it('rejects events with missing kind', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        reason: 'model_text_only',
      }),
    ).toBe(false);
  });

  it('rejects non-objects', () => {
    expect(isImagesSkippedEvent(null)).toBe(false);
    expect(isImagesSkippedEvent('images_skipped')).toBe(false);
    expect(isImagesSkippedEvent(undefined)).toBe(false);
  });
});

const makeUserMessage = (
  id: string,
  attachments: Message['experimental_attachments'],
): Message => ({
  id,
  role: 'user',
  content: 'hi',
  experimental_attachments: attachments,
});

const makeAssistantMessage = (id: string): Message => ({
  id,
  role: 'assistant',
  content: 'hello',
});

describe('stampImagesSkippedOnLatestUserMessage', () => {
  it('stamps skipped on every image attachment of the latest user message', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        { name: 'a.png', contentType: 'image/png', url: 'http://a' },
        { name: 'b.pdf', contentType: 'application/pdf', url: 'http://b' },
      ]),
      makeAssistantMessage('2'),
    ];

    const result = stampImagesSkippedOnLatestUserMessage(messages);

    expect(result).not.toBe(messages);
    const updatedAttachments = result[0].experimental_attachments!;
    expect(updatedAttachments[0]).toMatchObject({
      name: 'a.png',
      skipped: { reason: 'model_text_only' },
    });
    expect(updatedAttachments[1]).toMatchObject({ name: 'b.pdf' });
    expect((updatedAttachments[1] as { skipped?: unknown }).skipped).toBe(
      undefined,
    );
  });

  it('returns the same reference when no images are present', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        { name: 'doc.pdf', contentType: 'application/pdf', url: 'http://x' },
      ]),
    ];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('returns the same reference when images are already stamped', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        {
          name: 'a.png',
          contentType: 'image/png',
          url: 'http://a',
          // already stamped by an earlier event
          ...({ skipped: { reason: 'model_text_only' } } as Record<
            string,
            unknown
          >),
        },
      ]),
    ];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('returns the same reference when there is no user message', () => {
    const messages: Message[] = [makeAssistantMessage('1')];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('only touches the latest user message', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        { name: 'old.png', contentType: 'image/png', url: 'http://old' },
      ]),
      makeAssistantMessage('2'),
      makeUserMessage('3', [
        { name: 'new.png', contentType: 'image/png', url: 'http://new' },
      ]),
    ];

    const result = stampImagesSkippedOnLatestUserMessage(messages);

    expect(result[0]).toBe(messages[0]); // untouched
    expect(result[2]).not.toBe(messages[2]);
    expect(
      (result[2].experimental_attachments![0] as { skipped?: unknown }).skipped,
    ).toEqual({ reason: 'model_text_only' });
  });
});

// jsdom ships none of the globals the SDK uses to read a streamed response.
// v8 serialize/deserialize stands in for structuredClone (it keeps the Date on
// `createdAt`, which a JSON round-trip would flatten to a string).
Object.assign(globalThis, {
  ReadableStream,
  TextDecoder,
  TextEncoder,
  structuredClone: <T,>(value: T): T => deserialize(serialize(value)) as T,
});

const CHAT_API = 'chats/conv-1/conversation/';

// A turn cut short right after the `summarize` tool returned: the summary
// landed, the answer never started, and no `f:` (start_step) closes the
// message. That shape is what makes the SDK's multi-step continuation kick in.
const INTERRUPTED_AFTER_SUMMARY = [
  '9:{"toolCallId":"c1","toolName":"summarize","args":{"state":"running","summary_scope":"conversation"}}\n',
  'a:{"toolCallId":"c1","result":{"state":"done"}}\n',
].join('');

const streamOf = (payload: string) =>
  new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    },
  });

describe('useChat multi-step continuation', () => {
  const fetchAPIMock = jest.requireMock('@/api').fetchAPI as jest.Mock;

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {children}
    </QueryClientProvider>
  );

  it('does not re-POST the turn when a stream ends on a resolved tool call', async () => {
    const chatCalls: string[] = [];
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      chatCalls.push(url);
      return Promise.resolve({
        ok: true,
        body: streamOf(INTERRUPTED_AFTER_SUMMARY),
      });
    });

    const onError = jest.fn();
    const { result } = renderHook(
      () => useChat({ id: 'conv-1', api: CHAT_API, onError }),
      { wrapper },
    );

    await act(async () => {
      await result.current.append({ role: 'user', content: 'hello' });
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(onError).not.toHaveBeenCalled();

    // A second POST would carry an assistant-terminated message list, which the
    // backend answers with an empty stream — leaving the bubble blank.
    expect(chatCalls).toEqual([CHAT_API]);
  });
});
