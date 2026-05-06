import { useQuery } from '@tanstack/react-query';

import { fetchAPI } from '@/api';

export const KEY_PROJECT_ATTACHMENTS = 'project-attachments';

export interface ProjectAttachment {
  id: string;
  key: string;
  content_type: string;
  file_name: string;
  size: number | null;
  upload_state: string;
  url: string | null;
}

const getProjectAttachments = async (
  projectId: string,
): Promise<ProjectAttachment[]> => {
  const response = await fetchAPI(`projects/${projectId}/attachments/`);

  if (!response.ok) {
    throw new Error('Failed to fetch project attachments');
  }

  return response.json() as Promise<ProjectAttachment[]>;
};

export const useProjectAttachments = (projectId?: string) => {
  return useQuery<ProjectAttachment[]>({
    queryKey: [KEY_PROJECT_ATTACHMENTS, projectId],
    queryFn: () => getProjectAttachments(projectId as string),
    enabled: !!projectId,
  });
};
