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

const arenaFeature = vi.hoisted(() => ({ enabled: false }));

vi.mock('@/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/core')>()),
  useFeatureEnabled: (key: string) => key === 'arena' && arenaFeature.enabled,
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
const createConversation = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/features/chat/api/useCreateConversation', () => ({
  useCreateChatConversation: () => createConversation,
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

// Mirrors the wire shape emitted by `_report_forced_connector` in
// `pydantic_ai.py`: a `chat_notice`-kind `connector_unavailable` data part,
// kebab-cased to `data-connector-unavailable` on the wire, ahead of the
// answer text.
const CONNECTOR_UNAVAILABLE_STREAM = [
  'data: {"type":"start"}\n\n',
  'data: {"type":"data-connector-unavailable","data":{"type":"connector_unavailable","kind":"chat_notice","connector_id":"datagouv"},"transient":true}\n\n',
  'data: {"type":"text-start","id":"t1"}\n\n',
  'data: {"type":"text-delta","id":"t1","delta":"An answer without DataGouv."}\n\n',
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

const chatTree = (conversationId: string | undefined) => (
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
  </MemoryRouter>
);

const renderChat = (conversationId: string | undefined = 'conv-1') =>
  render(chatTree(conversationId));

const chatPostCount = (mock: Mock) =>
  mock.mock.calls.filter((call) => String(call[0]).includes('/conversation/'))
    .length;

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
    arenaFeature.enabled = false;
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

  it('keeps the question on screen when the history request fails', async () => {
    // Same rule as a resolved snapshot: a failed refetch must not clear a
    // conversation the client has already sent into.
    usePendingChatStore.setState({ input: 'Carried question' });
    getConversationMock.mockRejectedValue(new Error('boom'));

    renderChat();

    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(messageTexts()).toEqual([
        'You said: Carried question',
        'Assistant IA replied: An answer.',
      ]),
    );
  });

  it('sends once when submitted twice before the history resolves', async () => {
    // Submission waits for the in-flight history fetch, and until a send
    // actually starts the status stays `ready`, so the composer still accepts
    // Enter. Both submissions would otherwise resume on the same input.
    let resolveFetch: (value: { messages: [] }) => void = () => {};
    getConversationMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    renderChat();

    const box = screen.getByRole('textbox');
    await userEvent.type(box, 'Double send');
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{Enter}');

    await act(async () => {
      resolveFetch({ messages: [] });
    });

    await waitFor(() =>
      expect(messageTexts()).toEqual([
        'You said: Double send',
        'Assistant IA replied: An answer.',
      ]),
    );
    expect(chatPostCount(fetchAPIMock)).toBe(1);
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

  it('keeps a new comparison votable when the delayed initialization sees it running', async () => {
    arenaFeature.enabled = true;
    usePendingChatStore.setState({ input: 'Carried arena question' });
    let resolveFetch: (value: unknown) => void = () => {};
    getConversationMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.includes('/arena/draw/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ arena: true, comparison_id: 'running' }),
        });
      }
      if (url.includes('/vote/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              messages: HISTORY,
              pending_arena_comparison: null,
            }),
        });
      }
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      return Promise.resolve({ ok: true, body: streamOf(ANSWER_STREAM) });
    });
    renderChat();
    await waitFor(() => expect(chatPostCount(fetchAPIMock)).toBe(2));
    await act(async () => {
      resolveFetch({
        messages: [],
        pending_arena_comparison: {
          id: 'running',
          sides_finished: { left: false, right: false },
          restorable: false,
          answers: null,
        },
      });
    });
    const button = await screen.findByRole('button', {
      name: 'I prefer answer A',
    });
    await waitFor(() => expect(button).toBeEnabled());
    expect(
      fetchAPIMock.mock.calls.filter((call) =>
        String(call[0]).includes('/vote/'),
      ),
    ).toHaveLength(0);
    await userEvent.click(button);
    await waitFor(() =>
      expect(
        fetchAPIMock.mock.calls.filter((call) =>
          String(call[0]).includes('/vote/'),
        ),
      ).toHaveLength(1),
    );
    const vote = fetchAPIMock.mock.calls.find((call) =>
      String(call[0]).includes('/vote/'),
    );
    expect(JSON.parse(vote?.[1].body as string)).toEqual({ side: 'left' });
    const draw = fetchAPIMock.mock.calls.find((call) =>
      String(call[0]).includes('/arena/draw/'),
    );
    expect(JSON.parse(draw?.[1].body as string)).toMatchObject({
      message: {
        role: 'user',
        parts: [{ type: 'text', text: 'Carried arena question' }],
      },
    });
  });

  it('never abandons an unfinished comparison returned by a delayed handoff fetch', async () => {
    usePendingChatStore.setState({ input: 'Carried question' });
    let resolveFetch: (value: unknown) => void = () => {};
    getConversationMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    renderChat();
    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());
    await act(async () => {
      resolveFetch({
        messages: [],
        pending_arena_comparison: {
          id: 'running-comparison',
          sides_finished: { left: false, right: false },
          restorable: false,
          answers: null,
        },
      });
    });
    await waitFor(() =>
      expect(messageTexts()).toContain('You said: Carried question'),
    );
    expect(
      fetchAPIMock.mock.calls.filter((call) =>
        String(call[0]).includes('/vote/'),
      ),
    ).toHaveLength(0);
  });

  it("does not close another tab's unfinished comparison during initialization", async () => {
    getConversationMock.mockResolvedValue({
      messages: HISTORY,
      pending_arena_comparison: {
        id: 'other-tab',
        sides_finished: { left: true, right: false },
        restorable: false,
        answers: null,
      },
    });
    renderChat();
    await screen.findByText('An older answer');
    expect(
      fetchAPIMock.mock.calls.filter((call) =>
        String(call[0]).includes('/vote/'),
      ),
    ).toHaveLength(0);
  });

  it('puts an unvoted arena choice back on screen instead of resolving it', async () => {
    getConversationMock.mockResolvedValue({
      messages: [
        ...HISTORY,
        {
          id: 'server-u2',
          role: 'user' as const,
          parts: [{ type: 'text' as const, text: 'The compared question' }],
        },
      ],
      pending_arena_comparison: {
        id: 'cmp-1',
        sides_finished: { left: true, right: true },
        restorable: true,
        answers: {
          left: {
            id: 'a1',
            role: 'assistant' as const,
            parts: [{ type: 'text' as const, text: 'Stored left answer' }],
          },
          right: {
            id: 'a2',
            role: 'assistant' as const,
            parts: [{ type: 'text' as const, text: 'Stored right answer' }],
          },
        },
      },
    });

    renderChat();

    expect(await screen.findByText('Stored left answer')).toBeInTheDocument();
    expect(screen.getByText('Stored right answer')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'I prefer answer A' }),
    ).toBeEnabled();
    // Nothing was voted or abandoned behind the user's back.
    expect(
      fetchAPIMock.mock.calls.filter((call) =>
        String(call[0]).includes('/vote/'),
      ),
    ).toHaveLength(0);

    // And the conversation cannot move on until a side is picked.
    await act(async () => {
      await ask('Another question');
    });
    expect(chatPostCount(fetchAPIMock)).toBe(0);
    expect(
      screen.getByText(
        'Pick the answer you prefer above to continue this conversation.',
      ),
    ).toBeInTheDocument();
  });
});

describe('Chat arena lifecycle', () => {
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;
  const getConversationMock = vi.mocked(getConversation) as unknown as Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    arenaFeature.enabled = true;
    usePendingChatStore.setState({ input: '', files: null });
  });

  afterEach(() => {
    arenaFeature.enabled = false;
  });

  it('drops the comparison of the previous conversation on navigation', async () => {
    // conv-2's history is still loading: nothing of conv-1 may stay meanwhile.
    getConversationMock.mockImplementation(({ id }: { id: string }) =>
      id !== 'conv-1'
        ? new Promise(() => {})
        : Promise.resolve({
            messages: [
              ...HISTORY,
              {
                id: 'server-u2',
                role: 'user' as const,
                parts: [{ type: 'text' as const, text: 'Compared' }],
              },
            ],
            pending_arena_comparison: {
              id: 'cmp-1',
              sides_finished: { left: true, right: true },
              restorable: true,
              answers: {
                left: {
                  id: 'a1',
                  role: 'assistant' as const,
                  parts: [{ type: 'text' as const, text: 'Stored left' }],
                },
                right: {
                  id: 'a2',
                  role: 'assistant' as const,
                  parts: [{ type: 'text' as const, text: 'Stored right' }],
                },
              },
            },
          }),
    );

    const { rerender } = render(chatTree('conv-1'));
    expect(await screen.findByText('Stored left')).toBeInTheDocument();

    rerender(chatTree('conv-2'));

    await waitFor(() =>
      expect(screen.queryByText('Stored left')).not.toBeInTheDocument(),
    );
  });

  it('reloads the history from the server after stopping an arena turn', async () => {
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('/arena/draw/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ arena: true, comparison_id: 'cmp-running' }),
        });
      }
      if (url.includes('stop-streaming')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      // Candidate streams that never end on their own.
      return Promise.resolve({
        ok: true,
        body: new ReadableStream({ start() {} }),
      });
    });
    getConversationMock.mockResolvedValueOnce({
      messages: [...HISTORY],
      pending_arena_comparison: null,
    });

    renderChat();
    await screen.findByText('An older answer');
    await act(async () => {
      await ask('Stop me');
    });
    const stop = await screen.findByRole('button', { name: 'Stop' });

    getConversationMock.mockResolvedValue({
      messages: [
        ...HISTORY,
        {
          id: 'server-u2',
          role: 'user' as const,
          parts: [{ type: 'text' as const, text: 'Stop me' }],
        },
        {
          id: 'server-a2',
          role: 'assistant' as const,
          parts: [{ type: 'text' as const, text: 'Committed answer' }],
        },
      ],
    });
    await userEvent.click(stop);

    expect(await screen.findByText('Committed answer')).toBeInTheDocument();
  });

  // An arena turn whose two candidate streams end on their own.
  const mockFinishedArenaTurn = (
    vote: () => Promise<unknown>,
    cooldownSeconds: () => number = () => 0,
  ) =>
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: cooldownSeconds() }),
        });
      }
      if (url.includes('/arena/draw/')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ arena: true, comparison_id: 'cmp-1' }),
        });
      }
      if (url.includes('/vote/')) {
        return vote();
      }
      return Promise.resolve({ ok: true, body: streamOf(ANSWER_STREAM) });
    });
  const drawCount = () =>
    fetchAPIMock.mock.calls.filter((call) =>
      String(call[0]).includes('/arena/draw/'),
    ).length;

  it('reads the cooldown the candidate streams recorded once they are over', async () => {
    // The backend records the cooldown as the candidates complete.
    mockFinishedArenaTurn(
      () =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              messages: HISTORY,
              pending_arena_comparison: null,
            }),
        }),
      () => (chatPostCount(fetchAPIMock) === 2 ? 120 : 0),
    );
    getConversationMock.mockResolvedValue({
      messages: [],
      pending_arena_comparison: null,
    });

    renderChat();
    await act(async () => {
      await ask('Compare me');
    });
    const button = await screen.findByRole('button', {
      name: 'I prefer answer A',
    });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await screen.findByText('An older answer');

    await act(async () => {
      await ask('Too soon');
    });
    expect(drawCount()).toBe(1);
  });

  it('closes the split when the comparison was already closed elsewhere', async () => {
    mockFinishedArenaTurn(() =>
      Promise.resolve({
        ok: false,
        status: 409,
        headers: new Headers(),
        json: () => Promise.resolve({ error: 'closed' }),
      }),
    );
    getConversationMock.mockResolvedValueOnce({
      messages: [],
      pending_arena_comparison: null,
    });

    renderChat();
    await act(async () => {
      await ask('Voted in another tab');
    });
    const button = await screen.findByRole('button', {
      name: 'I prefer answer A',
    });
    await waitFor(() => expect(button).toBeEnabled());
    getConversationMock.mockResolvedValue({
      messages: HISTORY,
      pending_arena_comparison: null,
    });
    await userEvent.click(button);

    expect(await screen.findByText('An older answer')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'I prefer answer A' }),
    ).not.toBeInTheDocument();
  });

  it('draws once when a new chat is submitted twice before it is created', async () => {
    // Enter twice on a new chat: only the latest creation's callbacks run (as
    // with react-query's `mutate`), and the conversation page then sends the
    // message it finds in the pending store. The creating page must not send
    // it too, or a second comparison is drawn for the same question.
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('/arena/draw/')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ arena: true, comparison_id: 'cmp-1' }),
        });
      }
      return Promise.resolve({
        ok: true,
        body: new ReadableStream({ start() {} }),
      });
    });
    getConversationMock.mockResolvedValue({
      messages: [],
      pending_arena_comparison: null,
    });
    type Callbacks = { onSuccess: (data: { id: string }) => void };
    let latest: Callbacks | undefined;
    createConversation.mutate.mockImplementation(
      (_body: unknown, callbacks: Callbacks) => {
        latest = callbacks;
      },
    );
    const drawCount = () =>
      fetchAPIMock.mock.calls.filter((call) =>
        String(call[0]).includes('/arena/draw/'),
      ).length;

    const { unmount } = render(chatTree(undefined));
    await act(async () => {
      await ask('First question');
      await userEvent.keyboard('{Enter}');
    });
    expect(createConversation.mutate).toHaveBeenCalledTimes(2);

    await act(async () => {
      latest?.onSuccess({ id: 'conv-new' });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    unmount();
    renderChat('conv-new');

    await waitFor(() => expect(drawCount()).toBeGreaterThan(0));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(drawCount()).toBe(1);
  });
});

describe('Chat connector notices', () => {
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;
  const getConversationMock = vi.mocked(getConversation) as unknown as Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    usePendingChatStore.setState({ input: '', files: null });
    getConversationMock.mockResolvedValue({ messages: [] });
  });

  it('raises a toast, findable by its accessible name, when a forced connector was unreachable', async () => {
    // Drives the real stream-parsing path (DefaultChatTransport -> useChat's
    // onData -> Chat's onConnectorUnavailable -> showToast), the same one the
    // app uses, rather than calling the handler directly.
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        body: streamOf(CONNECTOR_UNAVAILABLE_STREAM),
      });
    });

    renderChat();

    await act(async () => {
      await ask('Force datagouv');
    });

    // `react-i18next` is mocked to `t: (key) => key`, so the translation key
    // is exactly the rendered, screen-reader-announced text: the toast lives
    // in a `aria-live="polite"` region, and this asserts on what a user (or
    // assistive tech) actually perceives, not on an internal `showToast` call.
    expect(
      await screen.findByText('DataGouv could not be reached'),
    ).toBeInTheDocument();
  });

  it('raises no toast when the connector was reachable', async () => {
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      return Promise.resolve({ ok: true, body: streamOf(ANSWER_STREAM) });
    });

    renderChat();

    await act(async () => {
      await ask('An ordinary question');
    });

    await waitFor(() =>
      expect(messageTexts()).toEqual([
        'You said: An ordinary question',
        'Assistant IA replied: An answer.',
      ]),
    );
    expect(
      screen.queryByText('DataGouv could not be reached'),
    ).not.toBeInTheDocument();
  });
});
