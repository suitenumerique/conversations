import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import fetchMock from 'fetch-mock';
import { PropsWithChildren } from 'react';

import { KEY_CONVERSATION } from '../useConversation';
import { KEY_LIST_CONVERSATION } from '../useConversations';
import { useRenameConversation } from '../useRenameConversation';

const API_BASE = 'http://test.jest/api/v1.0/';
const CONVERSATION_ID = 'conv-123';

describe('useRenameConversation', () => {
  let queryClient: QueryClient;

  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    fetchMock.restore();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  it('invalidates the conversation and list queries on success', async () => {
    fetchMock.put(`${API_BASE}chats/${CONVERSATION_ID}/`, 200);
    queryClient.setQueryData([KEY_CONVERSATION, CONVERSATION_ID], {
      id: CONVERSATION_ID,
      title: 'Original Title',
    });
    queryClient.setQueryData([KEY_LIST_CONVERSATION], []);

    const { result } = renderHook(() => useRenameConversation(), { wrapper });
    result.current.mutate({
      conversationId: CONVERSATION_ID,
      title: 'Updated Title',
    });

    // The collapsed left panel reads the title from the single-conversation
    // query, so it stays stale unless that key is invalidated too.
    await waitFor(() => {
      expect(
        queryClient.getQueryState([KEY_CONVERSATION, CONVERSATION_ID])
          ?.isInvalidated,
      ).toBe(true);
    });
    expect(
      queryClient.getQueryState([KEY_LIST_CONVERSATION])?.isInvalidated,
    ).toBe(true);
  });

  it('leaves other conversations untouched', async () => {
    fetchMock.put(`${API_BASE}chats/${CONVERSATION_ID}/`, 200);
    queryClient.setQueryData([KEY_CONVERSATION, 'other-conv'], {
      id: 'other-conv',
      title: 'Other Title',
    });

    const { result } = renderHook(() => useRenameConversation(), { wrapper });
    result.current.mutate({
      conversationId: CONVERSATION_ID,
      title: 'Updated Title',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(
      queryClient.getQueryState([KEY_CONVERSATION, 'other-conv'])
        ?.isInvalidated,
    ).toBe(false);
  });
});
