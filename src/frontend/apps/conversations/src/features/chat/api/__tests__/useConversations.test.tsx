import fetchMock from 'fetch-mock';

import { getConversations } from '../useConversations';

const API_BASE = 'http://test.jest/api/v1.0/';

describe('getConversations', () => {
  beforeEach(() => {
    fetchMock.restore();
  });

  it('sends project=none when title is not provided', async () => {
    fetchMock.get(`begin:${API_BASE}chats/`, {
      status: 200,
      body: { count: 0, results: [], next: null, previous: null },
    });

    await getConversations({ page: 1 });

    const url = fetchMock.lastUrl()!;
    expect(url).toContain('project=none');
    expect(url).not.toContain('title=');
  });

  it('omits project param when title is provided', async () => {
    fetchMock.get(`begin:${API_BASE}chats/`, {
      status: 200,
      body: { count: 0, results: [], next: null, previous: null },
    });

    await getConversations({ page: 1, title: 'search term' });

    const url = fetchMock.lastUrl()!;
    expect(url).not.toContain('project=');
    expect(url).toContain('title=search+term');
  });
});
