import {
  UseMutationOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_CONVERSATION } from './useConversation';
import { KEY_LIST_CONVERSATION } from './useConversations';
import { KEY_LIST_PROJECT } from './useProjects';

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
    onSuccess: (data, variables, onMutateResult, context) => {
      void queryClient.invalidateQueries({
        queryKey: [KEY_LIST_CONVERSATION],
      });
      void queryClient.invalidateQueries({
        queryKey: [KEY_LIST_PROJECT],
      });
      void queryClient.invalidateQueries({
        queryKey: [KEY_CONVERSATION, variables.conversationId],
      });
      if (options?.onSuccess) {
        void options.onSuccess(data, variables, onMutateResult, context);
      }
    },
    onError: (error, variables, onMutateResult, context) => {
      if (options?.onError) {
        void options.onError(error, variables, onMutateResult, context);
      }
    },
  });
};
