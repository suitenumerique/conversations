import {
  UseMutationOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_LIST_CONVERSATION } from './useConversations';

interface RemoveConversationProps {
  conversationId: string;
}

export const removeConversation = async ({
  conversationId,
}: RemoveConversationProps): Promise<void> => {
  const response = await fetchAPI(`chats/${conversationId}/`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to delete the conversation',
      await errorCauses(response),
    );
  }
};

type UseRemoveConversationOptions = UseMutationOptions<
  void,
  APIError,
  RemoveConversationProps
>;

export const useRemoveConversation = (
  options?: UseRemoveConversationOptions,
) => {
  const queryClient = useQueryClient();
  return useMutation<void, APIError, RemoveConversationProps>({
    mutationFn: removeConversation,
    ...options,
    onSuccess: (data, variables, context) => {
      void queryClient.invalidateQueries({
        queryKey: [KEY_LIST_CONVERSATION],
      });
      if (options?.onSuccess) {
        void options.onSuccess(data, variables, context);
      }
    },
    onError: (error, variables, context) => {
      if (options?.onError) {
        void options.onError(error, variables, context);
      }
    },
  });
};
