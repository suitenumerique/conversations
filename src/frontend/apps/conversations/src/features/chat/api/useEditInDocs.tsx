import { APIError, errorCauses, fetchAPI } from '@/api';

interface EditInDocsParams {
  conversationId: string;
  message_id: string;
}

export interface EditInDocsResponse {
  docId: string;
  docUrl: string;
}

export const editInDocs = async ({
  conversationId,
  message_id,
}: EditInDocsParams): Promise<EditInDocsResponse> => {
  const response = await fetchAPI(`chats/${conversationId}/edit-in-docs/`, {
    method: 'POST',
    body: JSON.stringify({
      message_id,
    }),
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to edit message in Docs',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<EditInDocsResponse>;
};
