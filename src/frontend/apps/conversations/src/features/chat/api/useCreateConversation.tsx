import { useMutation, useQueryClient } from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { ChatConversation } from '../types';

import { KEY_LIST_CONVERSATION } from './useConversations';
import { KEY_LIST_PROJECT } from './useProjects';

interface ChatConversationParams {
  title: string;
  project?: string;
}

export const createChatConversation = async ({
  title,
  project,
}: ChatConversationParams): Promise<ChatConversation> => {
  const body: Record<string, string> = { title };
  if (project) {
    body.project = project;
  }

  const response = await fetchAPI(`chats/`, {
    method: 'POST',
    body: JSON.stringify(body),
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
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: [KEY_LIST_CONVERSATION],
      });
      if (variables.project) {
        void queryClient.invalidateQueries({
          queryKey: [KEY_LIST_PROJECT],
        });
      }
    },
  });
}
