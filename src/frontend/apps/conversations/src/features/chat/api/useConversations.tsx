import {
  APIError,
  APIList,
  DefinedInitialDataInfiniteOptionsAPI,
  errorCauses,
  fetchAPI,
  useAPIInfiniteQuery,
} from '@/api';
import { ChatConversation } from '@/features/chat/types';

const _conversationsOrdering = [
  'created_at',
  '-created_at',
  'updated_at',
  '-updated_at',
] as const;

export type ConversationsOrdering = (typeof _conversationsOrdering)[number];

export type ConversationsParams = {
  page: number;
  ordering?: ConversationsOrdering;
  title?: string;
};

export type ConversationsResponse = APIList<ChatConversation>;

export const getConversations = async (
  params: ConversationsParams,
): Promise<ConversationsResponse> => {
  const searchParams = new URLSearchParams();
  if (params.page) {
    searchParams.set('page', params.page.toString());
  }

  if (params.ordering) {
    searchParams.set('ordering', params.ordering);
  }

  if (params.title) {
    searchParams.set('title', params.title);
  }

  if (!params.title) {
    searchParams.set('project', 'none');
  }

  const response = await fetchAPI(`chats/?${searchParams.toString()}`);

  if (!response.ok) {
    throw new APIError(
      'Failed to get the conversations',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<ConversationsResponse>;
};

export const KEY_LIST_CONVERSATION = 'conversations';

export const useInfiniteConversations = (
  params: ConversationsParams,
  queryConfig?: Partial<
    DefinedInitialDataInfiniteOptionsAPI<ConversationsResponse>
  >,
) => {
  return useAPIInfiniteQuery(
    KEY_LIST_CONVERSATION,
    getConversations,
    params,
    queryConfig as DefinedInitialDataInfiniteOptionsAPI<ConversationsResponse>,
  );
};
