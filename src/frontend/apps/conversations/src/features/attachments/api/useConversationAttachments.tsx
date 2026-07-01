import { useQuery } from '@tanstack/react-query';

import { fetchAPI } from '@/api';

export const KEY_CONVERSATION_ATTACHMENTS = 'conversation-attachments';

export interface ConversationAttachmentState {
  id: string;
  key: string;
  content_type: string;
  file_name: string;
  size: number | null;
  upload_state: string;
  index_state: string;
  url: string | null;
}

/**
 * An attachment is still being processed while it is being scanned
 * (`upload_state === 'analyzing'`) or indexed (`index_state === 'indexing'`).
 * Conversation files are uploaded at send time, so both phases run after the
 * upload returns - unlike project files, which are uploaded ahead of any chat.
 */
export const isAttachmentProcessing = (
  a: ConversationAttachmentState,
): boolean => a.upload_state === 'analyzing' || a.index_state === 'indexing';

const getConversationAttachments = async (
  conversationId: string,
): Promise<ConversationAttachmentState[]> => {
  const response = await fetchAPI(`chats/${conversationId}/attachments/`);

  if (!response.ok) {
    throw new Error('Failed to fetch conversation attachments');
  }

  return response.json() as Promise<ConversationAttachmentState[]>;
};

export const useConversationAttachments = (conversationId?: string) => {
  return useQuery<ConversationAttachmentState[]>({
    queryKey: [KEY_CONVERSATION_ATTACHMENTS, conversationId],
    queryFn: () => getConversationAttachments(conversationId as string),
    enabled: !!conversationId,
    // Poll while any file is still processing so the auto-send gate clears itself.
    refetchInterval: (query) =>
      query.state.data?.some(isAttachmentProcessing) ? 2000 : false,
  });
};
