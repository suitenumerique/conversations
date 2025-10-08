import {
  UseMutationOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_LIST_CONVERSATION } from './useConversations';

interface ScoreMessageParams {
  conversationId: string;
  message_id: string;
  value: 'positive' | 'negative';
}

export const scoreMessage = async ({
  conversationId,
  message_id,
  value,
}: ScoreMessageParams): Promise<void> => {
  const response = await fetchAPI(`chats/${conversationId}/score-message/`, {
    method: 'POST',
    body: JSON.stringify({
      message_id,
      value,
    }),
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to score the message',
      await errorCauses(response),
    );
  }
};
