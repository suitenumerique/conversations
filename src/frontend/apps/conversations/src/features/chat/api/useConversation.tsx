import { UseQueryOptions, useQuery } from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { ChatConversation } from '@/features/chat/types';

export type ConversationsParams = {
  id: string;
};

type ConversationResponse = ChatConversation;

export const getConversation = async ({
  id,
}: ConversationsParams): Promise<ConversationResponse> => {
  const response = await fetchAPI(`chats/${id}/`);

  if (!response.ok) {
    throw new APIError(
      'Failed to get the conversation',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<ConversationResponse>;
};

export const KEY_CONVERSATION = 'conversation';

export function useConversations(
  param: ConversationsParams,
  queryConfig?: UseQueryOptions<
    ConversationResponse,
    APIError,
    ConversationResponse
  >,
) {
  return useQuery<ConversationResponse, APIError, ConversationResponse>({
    queryKey: [KEY_CONVERSATION, param],
    queryFn: () => getConversation(param),
    ...queryConfig,
  });
}
