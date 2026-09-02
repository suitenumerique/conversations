/* eslint-disable testing-library/no-unnecessary-act, @typescript-eslint/require-await, testing-library/no-node-access */
import { ReadableStream } from 'node:stream/web';
import { TextDecoder, TextEncoder } from 'node:util';
import { deserialize, serialize } from 'node:v8';

import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Suspense } from 'react';
import { MemoryRouter } from 'react-router';
import type { Mock } from 'vitest';

import { fetchAPI } from '@/api';
import { ToastProvider } from '@/components/ToastProvider';
import { getConversation } from '@/features/chat/api/useConversation';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';

import { Chat } from '../Chat';

// jsdom implements no scrolling; the component scrolls to the latest message.
Element.prototype.scrollTo = () => {};

// jsdom ships none of the globals the SDK uses to read a streamed response.
Object.assign(globalThis, {
  ReadableStream,
  TextDecoder,
  TextEncoder,
  structuredClone: <T,>(value: T): T => deserialize(serialize(value)) as T,
});

vi.mock('@/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api')>()),
  fetchAPI: vi.fn(),
}));

vi.mock('@/features/chat/api/useConversation', () => ({
  getConversation: vi.fn(),
  KEY_CONVERSATION: 'conversation',
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// The markdown stack is ESM-only and irrelevant here: the assertions are about
// which messages are on screen, not how their text is rendered.
vi.mock('react-markdown', () => ({
  MarkdownHooks: ({ children }: { children: string }) => <div>{children}</div>,
}));
vi.mock('@shikijs/rehype/core', () => ({ default: () => {} }));
vi.mock('../../utils/shiki', () => ({
  getHighlighter: () => Promise.resolve({}),
}));
vi.mock('rehype-katex', () => ({ default: () => {} }));
vi.mock('remark-gfm', () => ({ default: () => {} }));
vi.mock('remark-math', () => ({ default: () => {} }));

vi.mock('@/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/core')>()),
  useConfig: () => ({ data: {} }),
}));
vi.mock('@/core/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/core/config')>()),
  useConfig: () => ({ data: {} }),
}));
vi.mock('@/features/chat/api/useAssistantHealth', () => ({
  useAssistantHealth: () => ({ data: undefined }),
}));
vi.mock('@/features/chat/api/useLLMConfiguration', () => ({
  useLLMConfiguration: () => ({ data: { models: [] } }),
}));
vi.mock('@/features/chat/api/useCreateConversation', () => ({
  useCreateChatConversation: () => ({ mutate: vi.fn() }),
}));
vi.mock('@/features/attachments/api/useProjectAttachments', () => ({
  useProjectAttachments: () => ({ data: undefined }),
}));
vi.mock('@/features/attachments/api/useReindexProjectAttachment', () => ({
  useReindexProjectAttachment: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/features/attachments/hooks/useUploadFile', () => ({
  useUploadFile: () => ({
    uploadFile: vi.fn(),
    isErrorAttachment: false,
    errorAttachment: undefined,
  }),
}));
vi.mock('@/features/sources-panel', () => ({
  useSourcePanelAnchor: () => null,
  SourcePanel: () => null,
}));

const ANSWER_STREAM = [
  'data: {"type":"start"}\n\n',
  'data: {"type":"text-start","id":"t1"}\n\n',
  'data: {"type":"text-delta","id":"t1","delta":"An answer."}\n\n',
  'data: {"type":"text-end","id":"t1"}\n\n',
  'data: {"type":"finish"}\n\n',
  'data: [DONE]\n\n',
].join('');

const streamOf = (payload: string) =>
  new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    },
  });

const HISTORY = [
  {
    id: 'server-u1',
    role: 'user' as const,
    parts: [{ type: 'text' as const, text: 'An older question' }],
  },
  {
    id: 'server-a1',
    role: 'assistant' as const,
    parts: [{ type: 'text' as const, text: 'An older answer' }],
  },
];

const renderChat = (conversationId: string | undefined = 'conv-1') =>
  render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <CunninghamProvider>
          <ToastProvider>
            <Suspense fallback={null}>
              <Chat initialConversationId={conversationId} />
            </Suspense>
          </ToastProvider>
        </CunninghamProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );

const messageTexts = () =>
  [...document.querySelectorAll('[data-message-id]')].map((el) =>
    el.textContent?.replace(/\s+/g, ' ').trim(),
  );

const ask = async (text: string) => {
  const box = screen.getByRole('textbox');
  await userEvent.type(box, text);
  await userEvent.keyboard('{Enter}');
};

describe('Chat message ownership', () => {
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;
  const getConversationMock = vi.mocked(getConversation) as unknown as Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    usePendingChatStore.setState({ input: '', files: null });
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      return Promise.resolve({ ok: true, body: streamOf(ANSWER_STREAM) });
    });
  });

  it('keeps the question on screen when a stale snapshot resolves mid-turn', async () => {
    // The real new-conversation handoff: the component auto-submits the carried
    // message, clears the pending input, and that re-runs the effect below.
    // Its snapshot was taken before the message was stored, and applying it
    // used to wipe the question until the next reload.
    usePendingChatStore.setState({ input: 'Carried question' });
    getConversationMock.mockResolvedValue({ messages: [] });

    renderChat();

    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(messageTexts()).toEqual([
        'You said: Carried question',
        'Assistant IA replied: An answer.',
      ]),
    );
  });

  it('replaces only the failed turn when retrying', async () => {
    // Retry used to remove the last assistant message, which is the previous
    // successful answer whenever the attempt failed before producing one, and
    // it left the question on screen twice.
    getConversationMock.mockResolvedValue({ messages: HISTORY });

    renderChat();
    await waitFor(() =>
      expect(messageTexts()).toEqual([
        'You said: An older question',
        'Assistant IA replied: An older answer',
      ]),
    );

    const cooldown = {
      ok: true,
      json: () => Promise.resolve({ cooldown_seconds: 0 }),
    };
    fetchAPIMock.mockImplementation((url: string) =>
      url.startsWith('chat-cooldown')
        ? Promise.resolve(cooldown)
        : Promise.resolve({ ok: false, status: 500 }),
    );

    await act(async () => {
      await ask('Second question');
    });

    const retry = await screen.findByRole('button', { name: 'Retry' });

    fetchAPIMock.mockImplementation((url: string) =>
      url.startsWith('chat-cooldown')
        ? Promise.resolve(cooldown)
        : Promise.resolve({ ok: true, body: streamOf(ANSWER_STREAM) }),
    );

    await act(async () => {
      await userEvent.click(retry);
    });

    await waitFor(() =>
      expect(messageTexts()).toEqual([
        'You said: An older question',
        'Assistant IA replied: An older answer',
        'You said: Second question',
        'Assistant IA replied: An answer.',
      ]),
    );
  });

  it('applies the fetched history even when a message is sent while it loads', async () => {
    // Switching conversations clears the messages and fetches the new history.
    // Sending inside that window used to leave the history unapplied, so the
    // conversation looked empty apart from the new exchange until a reload.
    let resolveFetch: (value: { messages: typeof HISTORY }) => void = () => {};
    getConversationMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    renderChat();

    // The submission is fully initiated while the fetch is still in flight.
    await act(async () => {
      await ask('Sent while loading');
    });

    await act(async () => {
      resolveFetch({ messages: HISTORY });
    });

    await waitFor(() =>
      expect(messageTexts()).toEqual([
        'You said: An older question',
        'Assistant IA replied: An older answer',
        'You said: Sent while loading',
        'Assistant IA replied: An answer.',
      ]),
    );
  });
});
