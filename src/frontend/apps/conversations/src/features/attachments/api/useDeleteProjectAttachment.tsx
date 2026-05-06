import { useMutation, useQueryClient } from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_PROJECT_ATTACHMENTS } from './useProjectAttachments';

interface DeleteProjectAttachmentParams {
  projectId: string;
  attachmentId: string;
}

const deleteProjectAttachment = async ({
  projectId,
  attachmentId,
}: DeleteProjectAttachmentParams): Promise<void> => {
  const response = await fetchAPI(
    `projects/${projectId}/attachments/${attachmentId}/`,
    { method: 'DELETE' },
  );

  if (!response.ok) {
    throw new APIError(
      'Failed to delete attachment',
      await errorCauses(response),
    );
  }
};

export const useDeleteProjectAttachment = (projectId: string) => {
  const queryClient = useQueryClient();
  return useMutation<void, APIError, string>({
    mutationFn: (attachmentId: string) =>
      deleteProjectAttachment({ projectId, attachmentId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [KEY_PROJECT_ATTACHMENTS, projectId],
      });
    },
  });
};
