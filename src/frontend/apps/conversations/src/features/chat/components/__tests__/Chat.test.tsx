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
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
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

const routerFlag = vi.hoisted(() => ({ enabled: false }));
vi.mock('@/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/core')>()),
  useConfig: () => ({ data: {} }),
  useFeatureEnabled: (key: string) => key === 'router' && routerFlag.enabled,
}));
vi.mock('@/core/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/core/config')>()),
  useConfig: () => ({ data: {} }),
}));
vi.mock('@/features/chat/api/useAssistantHealth', () => ({
  useAssistantHealth: () => ({ data: undefined }),
}));
const llmConfig = vi.hoisted(
  (): { data: { models: unknown[]; tiers?: unknown[] } | undefined } => ({
    data: { models: [] },
  }),
);
vi.mock('@/features/chat/api/useLLMConfiguration', () => ({
  useLLMConfiguration: () => ({ data: llmConfig.data }),
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
    llmConfig.data = { models: [] };
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
});

describe('Chat routing caption', () => {
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;
  const getConversationMock = vi.mocked(getConversation) as unknown as Mock;

  beforeEach(() => {
    vi.clearAllMocks();
    llmConfig.data = { models: [], tiers: [{ slug: 'auto' }] };
    routerFlag.enabled = true;
    usePendingChatStore.setState({ input: '', files: null });
    getConversationMock.mockResolvedValue({ messages: [] });
  });

  afterEach(() => {
    llmConfig.data = { models: [] };
    routerFlag.enabled = false;
    useChatPreferencesStore.setState({ selectedModelHrid: null });
  });

  it('routes a message sent before the LLM configuration has loaded', async () => {
    llmConfig.data = undefined;
    useChatPreferencesStore.setState({ selectedModelHrid: 'stored-model' });
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
    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());
    await ask('A routed question');

    await waitFor(() => expect(screen.getByText('An answer.')).toBeVisible());
    const chatUrls = fetchAPIMock.mock.calls
      .map((call) => String(call[0]))
      .filter((url) => url.includes('/conversation/'));
    expect(chatUrls).toEqual(['chats/conv-1/conversation/?tier=auto']);
  });

  it('hands the routing caption over to the answer bubble without doubling it', async () => {
    // The stream creates the (still empty) answer bubble on its `start` event,
    // while the chat status is still `submitted`: both the standalone caption
    // and the bubble's own one would be on screen in that window.
    let pushDelta: () => void = () => {};
    fetchAPIMock.mockImplementation((url: string) => {
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
            const encoder = new TextEncoder();
            // `start` carries a message id, so the SDK pushes the empty
            // assistant message and leaves the status on `submitted`.
            controller.enqueue(
              encoder.encode('data: {"type":"start","messageId":"a1"}\n\n'),
            );
            pushDelta = () => {
              controller.enqueue(encoder.encode(ANSWER_STREAM));
              controller.close();
            };
          },
        }),
      });
    });

    renderChat();
    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());
    await ask('A routed question');

    await waitFor(() =>
      expect(screen.getAllByTestId('routing-caption-pending')).toHaveLength(1),
    );
    await act(async () => {
      pushDelta();
    });
    await waitFor(() => expect(screen.getByText('An answer.')).toBeVisible());
  });
});

describe('Tier pin ownership', () => {
  const getConversationMock = vi.mocked(getConversation) as unknown as Mock;
  const tier = () => useChatPreferencesStore.getState().selectedTier;

  beforeEach(() => {
    vi.clearAllMocks();
    llmConfig.data = { models: [] };
    usePendingChatStore.setState({ input: '', files: null });
    useChatPreferencesStore.setState({
      selectedTier: 'auto',
      tierConversationId: null,
    });
    getConversationMock.mockResolvedValue({ messages: [] });
  });

  it('keeps the tier picked before the first message across the handoff', async () => {
    // The new-chat screen pins the tier with no conversation yet; creating one
    // hands the pin over and remounts the chat at /chat/<id>, which must not
    // snap the mode back to Auto right after sending.
    useChatPreferencesStore.setState({ tierConversationId: 'conv-1' });
    useChatPreferencesStore.getState().setSelectedTier('complex');
    usePendingChatStore.setState({ input: 'Carried question' });

    renderChat('conv-1');

    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());
    expect(tier()).toBe('complex');
  });

  it('keeps the tier while the conversation it was picked for stays open', async () => {
    renderChat('conv-1');
    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());

    act(() => {
      useChatPreferencesStore.getState().setSelectedTier('standard', 'conv-1');
    });

    await waitFor(() => expect(getConversationMock).toHaveBeenCalled());
    expect(tier()).toBe('standard');
  });

  it('goes back to Auto on another conversation', async () => {
    useChatPreferencesStore.setState({
      selectedTier: 'complex',
      tierConversationId: 'conv-1',
    });

    renderChat('conv-2');

    await waitFor(() => expect(tier()).toBe('auto'));
  });
});

describe('Tier pin restored from the conversation', () => {
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;
  const getConversationMock = vi.mocked(getConversation) as unknown as Mock;
  const chip = () => screen.getByTestId('tier-selector-chip');

  beforeEach(() => {
    vi.clearAllMocks();
    routerFlag.enabled = true;
    llmConfig.data = {
      models: [],
      tiers: [{ slug: 'auto' }, { slug: 'simple' }, { slug: 'standard' }],
    };
    usePendingChatStore.setState({ input: '', files: null });
    // A reload: the tier is not persisted, so the store starts on Auto.
    useChatPreferencesStore.setState({
      selectedTier: 'auto',
      tierConversationId: null,
    });
    getConversationMock.mockImplementation(({ id }: { id: string }) =>
      Promise.resolve({
        messages: [],
        pinned_tier: id === 'conv-1' ? 'simple' : null,
      }),
    );
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

  afterEach(() => {
    llmConfig.data = { models: [] };
    routerFlag.enabled = false;
  });

  it('shows the pinned tier after a reload and keeps it on the next turn', async () => {
    renderChat('conv-1');

    await waitFor(() => expect(chip()).toHaveTextContent('Fast'));
    await ask('A question after reload');

    await waitFor(() => expect(screen.getByText('An answer.')).toBeVisible());
    const chatUrls = fetchAPIMock.mock.calls
      .map((call) => String(call[0]))
      .filter((url) => url.includes('/conversation/'));
    expect(chatUrls).toEqual(['chats/conv-1/conversation/?tier=simple']);
  });

  it('shows Auto on another conversation without a pin', async () => {
    const view = renderChat('conv-1');
    await waitFor(() => expect(chip()).toHaveTextContent('Fast'));

    view.rerender(
      <MemoryRouter>
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <CunninghamProvider>
            <ToastProvider>
              <Suspense fallback={null}>
                <Chat initialConversationId="conv-2" />
              </Suspense>
            </ToastProvider>
          </CunninghamProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(getConversationMock).toHaveBeenCalledWith({ id: 'conv-2' }),
    );
    await waitFor(() => expect(chip()).toHaveTextContent('Auto'));
    expect(useChatPreferencesStore.getState().selectedTier).toBe('auto');
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
