import { useMutation, useQueryClient } from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { ChatConversation } from '../types';

import { KEY_LIST_CONVERSATION } from './useConversations';

interface ChatConversationParams {
  title: string;
}

export const createChatConversation = async ({
  title,
}: ChatConversationParams): Promise<ChatConversation> => {
  const response = await fetchAPI(`chats/`, {
    method: 'POST',
    body: JSON.stringify({
      title,
    }),
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to initiate a new chat conversation',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<ChatConversation>;
};

export function useCreateChatConversation() {
  const queryClient = useQueryClient();
  return useMutation<ChatConversation, APIError, ChatConversationParams>({
    mutationFn: createChatConversation,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [KEY_LIST_CONVERSATION],
      });
    },
  });
}
