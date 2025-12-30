import {
  UseMutationOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_LIST_CONVERSATION } from './useConversations';

interface RenameConversationProps {
  conversationId: string;
  title: string;
}

export const renameConversation = async ({
  conversationId,
  title,
}: RenameConversationProps): Promise<void> => {
  const response = await fetchAPI(`chats/${conversationId}/`, {
    method: 'PUT',
    body: JSON.stringify({
      title,
    }),
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to rename the conversation',
      await errorCauses(response),
    );
  }
};

type UseRenameConversationOptions = UseMutationOptions<
  void,
  APIError,
  RenameConversationProps
>;

export const useRenameConversation = (
  options?: UseRenameConversationOptions,
) => {
  const queryClient = useQueryClient();
  return useMutation<void, APIError, RenameConversationProps>({
    mutationFn: renameConversation,
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
