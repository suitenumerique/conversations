import { useMutation } from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { ConversationAttachment } from '../types';

interface CreateConversationAttachment {
  conversationId: string;
  content_type: string;
  file_name: string;
  size: number;
}

export const createConversationAttachment = async ({
  conversationId,
  content_type,
  file_name,
  size,
}: CreateConversationAttachment): Promise<ConversationAttachment> => {
  const response = await fetchAPI(`chats/${conversationId}/attachments/`, {
    method: 'POST',
    body: JSON.stringify({
      content_type: content_type,
      file_name: file_name,
      size: size,
    }),
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to upload on the doc',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<ConversationAttachment>;
};

export function useCreateConversationAttachment() {
  return useMutation<
    ConversationAttachment,
    APIError,
    CreateConversationAttachment
  >({
    mutationFn: createConversationAttachment,
  });
}
