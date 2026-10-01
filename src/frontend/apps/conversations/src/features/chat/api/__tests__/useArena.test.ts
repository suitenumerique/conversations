import type { Mock } from 'vitest';

import { fetchAPI } from '@/api';

import { drawArena, voteArena } from '../useArena';

vi.mock('@/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api')>()),
  fetchAPI: vi.fn(),
}));

const fetchAPIMock = vi.mocked(fetchAPI) as unknown as Mock;

describe('drawArena', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts the web search flag and returns the draw', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ arena: true, comparison_id: 'cmp-1' }),
    });

    const result = await drawArena('conv-1', true);

    expect(result).toEqual({ arena: true, comparison_id: 'cmp-1' });
    expect(fetchAPIMock).toHaveBeenCalledWith('chats/conv-1/arena/draw/', {
      method: 'POST',
      body: JSON.stringify({ force_web_search: true }),
    });
  });

  it('posts the selected model', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ arena: false }),
    });

    await drawArena('conv-1', false, undefined, 'model-a');

    expect(fetchAPIMock).toHaveBeenCalledWith('chats/conv-1/arena/draw/', {
      method: 'POST',
      body: JSON.stringify({ force_web_search: false, model_hrid: 'model-a' }),
    });
  });

  it('posts the data.gouv flag', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ arena: false }),
    });

    await drawArena('conv-1', false, undefined, null, true);

    expect(fetchAPIMock).toHaveBeenCalledWith('chats/conv-1/arena/draw/', {
      method: 'POST',
      body: JSON.stringify({ force_web_search: false, force_datagouv: true }),
    });
  });

  it('returns arena false when the backend says so', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ arena: false }),
    });

    expect(await drawArena('conv-1', false)).toEqual({ arena: false });
  });

  it('returns arena false when the request fails', async () => {
    fetchAPIMock.mockRejectedValue(new Error('network down'));

    expect(await drawArena('conv-1', false)).toEqual({ arena: false });
  });

  it('returns arena false on a non-2xx response', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: false,
      status: 500,
      headers: { get: () => null },
      json: () => Promise.resolve({ detail: 'boom' }),
    });

    expect(await drawArena('conv-1', false)).toEqual({ arena: false });
  });

  it('returns arena false on a malformed payload', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ arena: true }),
    });

    expect(await drawArena('conv-1', false)).toEqual({ arena: false });
  });
});

describe('voteArena', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts the side and returns the conversation', async () => {
    const conversation = { id: 'conv-1', messages: [] };
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(conversation),
    });

    const result = await voteArena('conv-1', 'cmp-1', 'right');

    expect(result).toEqual({ conversation, acknowledgement: null });
    expect(fetchAPIMock).toHaveBeenCalledWith(
      'chats/conv-1/arena/cmp-1/vote/',
      { method: 'POST', body: JSON.stringify({ side: 'right' }) },
    );
  });

  it('splits the acknowledgement block off the conversation', async () => {
    const conversation = { id: 'conv-1', messages: [] };
    const acknowledgement = {
      user_votes: 7,
      experiment_votes: 1342,
      milestone: 'first_vote',
    };
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ...conversation, acknowledgement }),
    });

    const result = await voteArena('conv-1', 'cmp-1', 'left');

    expect(result).toEqual({ conversation, acknowledgement });
  });

  it('ignores a malformed acknowledgement', async () => {
    const conversation = { id: 'conv-1', messages: [] };
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({ ...conversation, acknowledgement: { foo: 1 } }),
    });

    const result = await voteArena('conv-1', 'cmp-1', 'left');

    expect(result).toEqual({ conversation, acknowledgement: null });
  });

  it('posts a null side to abandon', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'conv-1', messages: [] }),
    });

    await voteArena('conv-1', 'cmp-1', null);

    expect(fetchAPIMock.mock.calls[0][1]).toMatchObject({
      body: JSON.stringify({ side: null }),
    });
  });

  it('throws on a non-2xx response', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: false,
      status: 409,
      headers: { get: () => null },
      json: () => Promise.resolve({ detail: 'closed' }),
    });

    await expect(voteArena('conv-1', 'cmp-1', 'left')).rejects.toThrow(
      'Failed to record the arena vote',
    );
  });
});
