import { ReadableStream } from 'node:stream/web';
import { TextDecoder, TextEncoder } from 'node:util';
import { deserialize, serialize } from 'node:v8';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { FileUIPart, UIMessage } from 'ai';
import type { Mock } from 'vitest';

import { fetchAPI } from '@/api';

import {
  isImagesSkippedEvent,
  stampImagesSkippedOnLatestUserMessage,
  useChat,
} from '../useChat';

vi.mock('@/api', () => ({
  fetchAPI: vi.fn(),
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

const filePart = (
  filename: string,
  mediaType: string,
  url: string,
  extra: Record<string, unknown> = {},
): FileUIPart => ({ type: 'file', filename, mediaType, url, ...extra });

const makeUserMessage = (id: string, files: FileUIPart[]): UIMessage => ({
  id,
  role: 'user',
  parts: [{ type: 'text', text: 'hi' }, ...files],
});

const makeAssistantMessage = (id: string): UIMessage => ({
  id,
  role: 'assistant',
  parts: [{ type: 'text', text: 'hello' }],
});

const filePartsOf = (message: UIMessage): FileUIPart[] =>
  message.parts.filter((part): part is FileUIPart => part.type === 'file');

describe('stampImagesSkippedOnLatestUserMessage', () => {
  it('stamps skipped on every image file part of the latest user message', () => {
    const messages: UIMessage[] = [
      makeUserMessage('1', [
        filePart('a.png', 'image/png', 'http://a'),
        filePart('b.pdf', 'application/pdf', 'http://b'),
      ]),
      makeAssistantMessage('2'),
    ];

    const result = stampImagesSkippedOnLatestUserMessage(messages);

    expect(result).not.toBe(messages);
    const updatedFiles = filePartsOf(result[0]);
    expect(updatedFiles[0]).toMatchObject({
      filename: 'a.png',
      skipped: { reason: 'model_text_only' },
    });
    expect(updatedFiles[1]).toMatchObject({ filename: 'b.pdf' });
    expect((updatedFiles[1] as { skipped?: unknown }).skipped).toBe(undefined);
  });

  it('returns the same reference when no images are present', () => {
    const messages: UIMessage[] = [
      makeUserMessage('1', [
        filePart('doc.pdf', 'application/pdf', 'http://x'),
      ]),
    ];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('returns the same reference when images are already stamped', () => {
    const messages: UIMessage[] = [
      makeUserMessage('1', [
        // already stamped by an earlier event
        filePart('a.png', 'image/png', 'http://a', {
          skipped: { reason: 'model_text_only' },
        }),
      ]),
    ];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('returns the same reference when there is no user message', () => {
    const messages: UIMessage[] = [makeAssistantMessage('1')];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('only touches the latest user message', () => {
    const messages: UIMessage[] = [
      makeUserMessage('1', [filePart('old.png', 'image/png', 'http://old')]),
      makeAssistantMessage('2'),
      makeUserMessage('3', [filePart('new.png', 'image/png', 'http://new')]),
    ];

    const result = stampImagesSkippedOnLatestUserMessage(messages);

    expect(result[0]).toBe(messages[0]); // untouched
    expect(result[2]).not.toBe(messages[2]);
    expect(
      (filePartsOf(result[2])[0] as { skipped?: unknown }).skipped,
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
// landed, the answer never started, and no `finish` closes the message. That
// shape is what an SDK configured to continue multi-step turns would re-POST.
const INTERRUPTED_AFTER_SUMMARY = [
  'data: {"type":"start"}\n\n',
  'data: {"type":"tool-input-available","toolCallId":"c1","toolName":"summarize"',
  ',"input":{"state":"running","summary_scope":"conversation"}}\n\n',
  'data: {"type":"tool-output-available","toolCallId":"c1","output":{"state":"done"}}\n\n',
  'data: [DONE]\n\n',
].join('');

const streamOf = (payload: string) =>
  new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    },
  });

describe('useChat multi-step continuation', () => {
  // Cast away the signature: the stubs below return partial Response objects,
  // as they did under the previous `jest.Mock` cast.
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;

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

    const onError = vi.fn();
    const { result } = renderHook(
      () => useChat({ id: 'conv-1', api: CHAT_API, onError }),
      { wrapper },
    );

    await act(async () => {
      await result.current.sendMessage({ text: 'hello' });
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(onError).not.toHaveBeenCalled();

    // A second POST would carry an assistant-terminated message list, which the
    // backend answers with an empty stream — leaving the bubble blank.
    expect(chatCalls).toEqual([CHAT_API]);
  });
});

// The exact frames the backend emits for a turn with a tool call, a source, a
// cooldown notice and a CO2 impact — copied from the encoder's golden test.
const FULL_TURN = [
  'data: {"type":"start","messageId":"trace-abc"}\n\n',
  'data: {"type":"tool-input-available","toolCallId":"c1","toolName":"document_search_rag"',
  ',"input":{"query":"what?"}}\n\n',
  'data: {"type":"source-url","sourceId":"s1","url":"https://example.test"}\n\n',
  'data: {"type":"tool-output-available","toolCallId":"c1","output":{"state":"done"}}\n\n',
  'data: {"type":"text-start","id":"0"}\n\n',
  'data: {"type":"text-delta","id":"0","delta":"Hello"}\n\n',
  'data: {"type":"text-delta","id":"0","delta":" there"}\n\n',
  'data: {"type":"text-end","id":"0"}\n\n',
  'data: {"type":"data-cooldown","data":{"type":"cooldown","seconds":30}',
  ',"transient":true}\n\n',
  'data: {"type":"data-images-skipped","data":{"type":"images_skipped"',
  ',"kind":"chat_notice","reason":"model_text_only"},"transient":true}\n\n',
  'data: {"type":"finish","messageMetadata":{"usage":{"promptTokens":10',
  ',"completionTokens":3,"co2Impact":0.5},"co2_impact":0.5}}\n\n',
  'data: [DONE]\n\n',
].join('');

describe('useChat against a backend stream', () => {
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {children}
    </QueryClientProvider>
  );

  it('builds the message, its metadata and the transient notices', async () => {
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      return Promise.resolve({ ok: true, body: streamOf(FULL_TURN) });
    });

    const onImagesSkipped = vi.fn();
    const { result } = renderHook(
      () => useChat({ id: 'conv-1', api: CHAT_API, onImagesSkipped }),
      { wrapper },
    );

    // Let the chat-cooldown query settle first: it resets cooldownUntil, and
    // landing after the stream would clobber the value the frame carries.
    await waitFor(() =>
      expect(fetchAPIMock).toHaveBeenCalledWith('chat-cooldown/'),
    );

    await act(async () => {
      await result.current.sendMessage({ text: 'hello' });
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    const assistant = result.current.messages.at(-1)!;
    // The message id the backend announced, which the feedback buttons key on.
    expect(assistant.id).toBe('trace-abc');
    expect(assistant.parts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: 'text', text: 'Hello there' }),
        expect.objectContaining({
          type: 'source-url',
          sourceId: 's1',
          url: 'https://example.test',
        }),
        expect.objectContaining({
          type: 'tool-document_search_rag',
          state: 'output-available',
          output: { state: 'done' },
        }),
      ]),
    );
    expect(assistant.metadata).toMatchObject({ co2_impact: 0.5 });

    // Transient data parts reach the callbacks without polluting the message.
    expect(onImagesSkipped).toHaveBeenCalledWith('chat_notice');
    expect(result.current.cooldownUntil).toBeGreaterThan(Date.now());
    expect(assistant.parts.some((part) => part.type.startsWith('data-'))).toBe(
      false,
    );
  });
});
