import { useMutation, useQueryClient } from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_PROJECT_ATTACHMENTS } from './useProjectAttachments';

interface ReindexProjectAttachmentParams {
  projectId: string;
  attachmentId: string;
}

const reindexProjectAttachment = async ({
  projectId,
  attachmentId,
}: ReindexProjectAttachmentParams): Promise<void> => {
  const response = await fetchAPI(
    `projects/${projectId}/attachments/${attachmentId}/reindex/`,
    { method: 'POST' },
  );

  if (!response.ok) {
    throw new APIError(
      'Failed to reindex attachment',
      await errorCauses(response),
    );
  }
};

export const useReindexProjectAttachment = (projectId: string) => {
  const queryClient = useQueryClient();
  return useMutation<void, APIError, string[]>({
    mutationFn: async (attachmentIds: string[]) => {
      await Promise.all(
        attachmentIds.map((attachmentId) =>
          reindexProjectAttachment({ projectId, attachmentId }),
        ),
      );
    },
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: [KEY_PROJECT_ATTACHMENTS, projectId],
      });
    },
  });
};
