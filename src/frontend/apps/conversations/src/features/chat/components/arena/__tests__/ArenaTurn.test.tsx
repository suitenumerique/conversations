import { ReadableStream } from 'node:stream/web';
import { TextDecoder, TextEncoder } from 'node:util';
import { deserialize, serialize } from 'node:v8';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UIMessage } from 'ai';
import type { Mock } from 'vitest';

import { fetchAPI } from '@/api';
import { ArenaAcknowledgement } from '@/features/chat/api/useArena';

import { ArenaTurn } from '../ArenaTurn';

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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// The markdown stack is ESM-only and irrelevant here.
vi.mock('react-markdown', () => ({
  MarkdownHooks: ({ children }: { children: string }) => <div>{children}</div>,
}));
vi.mock('@shikijs/rehype/core', () => ({ default: () => {} }));
vi.mock('../../../utils/shiki', () => ({
  getHighlighter: () => Promise.resolve({}),
}));
vi.mock('rehype-katex', () => ({ default: () => {} }));
vi.mock('remark-gfm', () => ({ default: () => {} }));
vi.mock('remark-math', () => ({ default: () => {} }));

vi.mock('@/core/config', () => ({
  useConfig: () => ({ data: {} }),
}));

const answerStream = (text: string) =>
  [
    'data: {"type":"start"}\n\n',
    'data: {"type":"text-start","id":"t1"}\n\n',
    `data: {"type":"text-delta","id":"t1","delta":${JSON.stringify(text)}}\n\n`,
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

/** A stream that only ends when `finish()` is called. */
const heldStream = (payload: string) => {
  let finish = () => {};
  const stream = new ReadableStream({
    start(controller) {
      finish = () => {
        controller.enqueue(new TextEncoder().encode(payload));
        controller.close();
      };
    },
  });
  return { stream, finish: () => finish() };
};

const HISTORY: UIMessage[] = [
  {
    id: 'u0',
    role: 'user',
    parts: [{ type: 'text', text: 'An older question' }],
  },
  {
    id: 'a0',
    role: 'assistant',
    parts: [{ type: 'text', text: 'An older answer' }],
  },
];

const CONVERSATION = {
  id: 'conv-1',
  messages: [...HISTORY],
  created_at: '',
  updated_at: '',
};

const renderTurn = (props: Partial<React.ComponentProps<typeof ArenaTurn>>) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ArenaTurn
        conversationId="conv-1"
        comparisonId="cmp-1"
        userText="Which one?"
        history={HISTORY}
        onVoted={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  );

const ACK: ArenaAcknowledgement = {
  user_votes: 7,
  experiment_votes: 1342,
  milestone: null,
};

const RESTORED = {
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
};

/** Answer the cooldown probe and the vote; nothing else may be called. */
const mockRestoredVote = (
  fetchAPIMock: Mock,
  voteBody: unknown = CONVERSATION,
) => {
  fetchAPIMock.mockImplementation((url: string) => {
    if (url.startsWith('chat-cooldown')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cooldown_seconds: 0 }),
      });
    }
    if (url.includes('/arena/')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(voteBody),
      });
    }
    throw new Error(`unexpected call to ${url}`);
  });
};

/** Let the vote request and its `.json()` settle under fake timers. */
const flushPromises = () =>
  act(async () => {
    for (let i = 0; i < 10; i++) {
      await Promise.resolve();
    }
  });

const voteButtons = () => ({
  left: screen.getByRole('button', { name: 'I prefer answer A' }),
  right: screen.getByRole('button', { name: 'I prefer answer B' }),
});

describe('ArenaTurn', () => {
  const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('streams both sides with their own query params and renders two columns', async () => {
    const chatCalls: string[] = [];
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      chatCalls.push(url);
      const side = url.includes('arena_side=left')
        ? 'Left answer'
        : 'Right answer';
      return Promise.resolve({ ok: true, body: streamOf(answerStream(side)) });
    });

    renderTurn({});

    expect(screen.getByText('Answer A')).toBeInTheDocument();
    expect(screen.getByText('Answer B')).toBeInTheDocument();

    expect(await screen.findByText('Left answer')).toBeInTheDocument();
    expect(screen.getByText('Right answer')).toBeInTheDocument();

    expect(chatCalls.sort()).toEqual([
      'chats/conv-1/conversation/?arena_comparison=cmp-1&arena_side=left',
      'chats/conv-1/conversation/?arena_comparison=cmp-1&arena_side=right',
    ]);
    // Candidates never carry the copy/feedback bar.
    expect(
      screen.queryByRole('button', { name: 'Copy' }),
    ).not.toBeInTheDocument();
  });

  it('renders a restored comparison without streaming anything again', async () => {
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      throw new Error(`unexpected call to ${url}`);
    });

    renderTurn({
      restoredAnswers: {
        left: {
          id: 'a1',
          role: 'assistant',
          parts: [{ type: 'text', text: 'Stored left answer' }],
        },
        right: {
          id: 'a2',
          role: 'assistant',
          parts: [{ type: 'text', text: 'Stored right answer' }],
        },
      },
    });

    expect(await screen.findByText('Stored left answer')).toBeInTheDocument();
    expect(screen.getByText('Stored right answer')).toBeInTheDocument();
    // The choice is live right away: nothing to wait for.
    expect(voteButtons().left).toBeEnabled();
    expect(voteButtons().right).toBeEnabled();
  });

  it('keeps both vote buttons disabled until both sides are ready', async () => {
    const held = heldStream(answerStream('Right answer'));
    fetchAPIMock.mockImplementation((url: string) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('arena_side=left')) {
        return Promise.resolve({
          ok: true,
          body: streamOf(answerStream('Left answer')),
        });
      }
      return Promise.resolve({ ok: true, body: held.stream });
    });

    const onStreamingChange = vi.fn();
    renderTurn({ onStreamingChange });

    expect(await screen.findByText('Left answer')).toBeInTheDocument();
    expect(voteButtons().left).toBeDisabled();
    expect(voteButtons().right).toBeDisabled();
    expect(onStreamingChange).toHaveBeenLastCalledWith(true);

    held.finish();

    await waitFor(() => expect(voteButtons().left).toBeEnabled());
    expect(voteButtons().right).toBeEnabled();
    await waitFor(() =>
      expect(onStreamingChange).toHaveBeenLastCalledWith(false),
    );
  });

  it('votes for the clicked side and hands the conversation back', async () => {
    const voteCalls: { url: string; body: string }[] = [];
    fetchAPIMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('/arena/')) {
        voteCalls.push({ url, body: init?.body as string });
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(CONVERSATION),
        });
      }
      return Promise.resolve({
        ok: true,
        body: streamOf(answerStream('An answer')),
      });
    });

    const onVoted = vi.fn();
    renderTurn({ onVoted });

    await waitFor(() => expect(voteButtons().right).toBeEnabled());
    await userEvent.click(voteButtons().right);

    await waitFor(() =>
      expect(onVoted).toHaveBeenCalledWith(CONVERSATION, null),
    );
    expect(voteCalls).toEqual([
      {
        url: 'chats/conv-1/arena/cmp-1/vote/',
        body: JSON.stringify({ side: 'right' }),
      },
    ]);
  });

  it('does not vote when an answer column is clicked', async () => {
    const bodies: string[] = [];
    fetchAPIMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('/arena/')) {
        bodies.push(init?.body as string);
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(CONVERSATION),
        });
      }
      return Promise.resolve({
        ok: true,
        body: streamOf(answerStream('An answer')),
      });
    });

    const onVoted = vi.fn();
    renderTurn({ onVoted });

    await waitFor(() => expect(voteButtons().right).toBeEnabled());
    await userEvent.click(screen.getByTestId('arena-side-right'));

    // Only the two buttons of the vote bar cast a vote.
    expect(bodies).toEqual([]);
    expect(onVoted).not.toHaveBeenCalled();

    await userEvent.click(voteButtons().right);
    await waitFor(() =>
      expect(onVoted).toHaveBeenCalledWith(CONVERSATION, null),
    );
    expect(bodies).toEqual([JSON.stringify({ side: 'right' })]);
  });

  it('abandons the comparison when a side fails', async () => {
    const voteCalls: string[] = [];
    fetchAPIMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('/arena/')) {
        voteCalls.push(init?.body as string);
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(CONVERSATION),
        });
      }
      if (url.includes('arena_side=right')) {
        return Promise.reject(new Error('model_unavailable'));
      }
      return Promise.resolve({
        ok: true,
        body: streamOf(answerStream('Left answer')),
      });
    });

    const onAbandoned = vi.fn();
    const onVoted = vi.fn();
    renderTurn({ onAbandoned, onVoted });

    await waitFor(() => expect(onAbandoned).toHaveBeenCalledWith(CONVERSATION));
    expect(voteCalls).toEqual([JSON.stringify({ side: null })]);
    expect(onVoted).not.toHaveBeenCalled();
  });

  it('abandons the comparison when a stream ends without an answer', async () => {
    // The run failed server-side once the response had started: the stream
    // is cut after `start`, so the side settles with nothing to vote for.
    const voteCalls: string[] = [];
    fetchAPIMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('/arena/')) {
        voteCalls.push(init?.body as string);
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(CONVERSATION),
        });
      }
      return Promise.resolve({
        ok: true,
        body: streamOf(
          url.includes('arena_side=right')
            ? 'data: {"type":"start","messageId":"m-right"}\n\n'
            : answerStream('Left answer'),
        ),
      });
    });

    const onAbandoned = vi.fn();
    const onVoted = vi.fn();
    renderTurn({ onAbandoned, onVoted });

    await waitFor(() => expect(onAbandoned).toHaveBeenCalledWith(CONVERSATION));
    expect(voteCalls).toEqual([JSON.stringify({ side: null })]);
    expect(onVoted).not.toHaveBeenCalled();
  });

  it('abandons the comparison when a side only shows a tool part', async () => {
    // A run that stops after a failed document parsing (or a busy reindex)
    // ends `ready` with a tool part and no text: it is a failed side.
    const voteCalls: string[] = [];
    fetchAPIMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith('chat-cooldown')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cooldown_seconds: 0 }),
        });
      }
      if (url.includes('/arena/')) {
        voteCalls.push(init?.body as string);
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(CONVERSATION),
        });
      }
      return Promise.resolve({
        ok: true,
        body: streamOf(
          url.includes('arena_side=right')
            ? [
                'data: {"type":"start","messageId":"m-right"}\n\n',
                'data: {"type":"tool-input-available","toolCallId":"c1","toolName":"document_parsing","input":{}}\n\n',
                'data: {"type":"tool-output-available","toolCallId":"c1","output":{"state":"error"}}\n\n',
                'data: {"type":"finish"}\n\n',
                'data: [DONE]\n\n',
              ].join('')
            : answerStream('Left answer'),
        ),
      });
    });

    const onAbandoned = vi.fn();
    const onVoted = vi.fn();
    renderTurn({ onAbandoned, onVoted });

    await waitFor(() => expect(onAbandoned).toHaveBeenCalledWith(CONVERSATION));
    expect(voteCalls).toEqual([JSON.stringify({ side: null })]);
    expect(onVoted).not.toHaveBeenCalled();
  });

  describe('vote transition', () => {
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    });

    afterEach(() => {
      vi.useRealTimers();
      // @ts-expect-error jsdom has no matchMedia; tests set it up when needed.
      delete window.matchMedia;
    });

    it('hides the bar, collapses the loser and defers onVoted until the fallback timer', async () => {
      mockRestoredVote(fetchAPIMock, { ...CONVERSATION, acknowledgement: ACK });
      const onVoted = vi.fn();
      renderTurn({ onVoted, restoredAnswers: RESTORED });

      fireEvent.click(voteButtons().right);
      await flushPromises();

      // Bar gone, columns locked, loser fading, winner caption fading.
      expect(
        screen.queryByRole('button', { name: 'I prefer answer A' }),
      ).not.toBeInTheDocument();
      expect(screen.getByTestId('arena-side-left')).toHaveAttribute(
        'data-arena-state',
        'loser',
      );
      expect(screen.getByTestId('arena-side-left')).toHaveAttribute(
        'aria-hidden',
        'true',
      );
      expect(screen.getByTestId('arena-side-right')).toHaveAttribute(
        'data-arena-state',
        'winner',
      );
      // The vote is recorded but the parent is not told yet.
      expect(onVoted).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(319);
      });
      await flushPromises();
      expect(onVoted).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      await flushPromises();
      expect(onVoted).toHaveBeenCalledTimes(1);
      expect(onVoted).toHaveBeenCalledWith(CONVERSATION, ACK);
    });

    it('fires onVoted as soon as the grid transition ends', async () => {
      mockRestoredVote(fetchAPIMock);
      const onVoted = vi.fn();
      renderTurn({ onVoted, restoredAnswers: RESTORED });

      fireEvent.click(voteButtons().left);
      await flushPromises();
      expect(onVoted).not.toHaveBeenCalled();

      // An unrelated property ending does not count.
      fireEvent.transitionEnd(screen.getByTestId('arena-split'), {
        propertyName: 'gap',
      });
      await flushPromises();
      expect(onVoted).not.toHaveBeenCalled();

      fireEvent.transitionEnd(screen.getByTestId('arena-split'), {
        propertyName: 'grid-template-columns',
      });
      await flushPromises();
      expect(onVoted).toHaveBeenCalledWith(CONVERSATION, null);
    });

    it('waits for the vote response even when the transition is already over', async () => {
      let resolveVote: (value: unknown) => void = () => {};
      fetchAPIMock.mockImplementation((url: string) => {
        if (url.startsWith('chat-cooldown')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ cooldown_seconds: 0 }),
          });
        }
        return new Promise((resolve) => {
          resolveVote = resolve;
        });
      });
      const onVoted = vi.fn();
      renderTurn({ onVoted, restoredAnswers: RESTORED });

      fireEvent.click(voteButtons().left);
      act(() => {
        vi.advanceTimersByTime(320);
      });
      await flushPromises();
      expect(onVoted).not.toHaveBeenCalled();

      resolveVote({ ok: true, json: () => Promise.resolve(CONVERSATION) });
      await flushPromises();
      expect(onVoted).toHaveBeenCalledWith(CONVERSATION, null);
    });

    it('uses a short cross-fade only under reduced motion', async () => {
      window.matchMedia = vi.fn().mockReturnValue({ matches: true });
      mockRestoredVote(fetchAPIMock);
      const onVoted = vi.fn();
      renderTurn({ onVoted, restoredAnswers: RESTORED });

      fireEvent.click(voteButtons().right);
      await flushPromises();
      expect(onVoted).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(170);
      });
      await flushPromises();
      expect(onVoted).toHaveBeenCalledWith(CONVERSATION, null);
    });

    it('puts the columns and the bar back when the vote fails', async () => {
      fetchAPIMock.mockImplementation((url: string) => {
        if (url.startsWith('chat-cooldown')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ cooldown_seconds: 0 }),
          });
        }
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({}),
        });
      });
      const onVoted = vi.fn();
      const onError = vi.fn();
      renderTurn({ onVoted, onError, restoredAnswers: RESTORED });

      fireEvent.click(voteButtons().left);
      await flushPromises();

      expect(onError).toHaveBeenCalledTimes(1);
      expect(onVoted).not.toHaveBeenCalled();
      expect(screen.getByTestId('arena-side-right')).not.toHaveAttribute(
        'data-arena-state',
      );
      expect(voteButtons().left).toBeEnabled();
    });
  });
});
