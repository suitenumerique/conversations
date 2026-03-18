import {
  UseMutationOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_LIST_PROJECT } from './useProjects';

interface UpdateProjectProps {
  projectId: string;
  title?: string;
  icon?: string;
  color?: string;
  llm_instructions?: string;
}

export const updateProject = async ({
  projectId,
  ...fields
}: UpdateProjectProps): Promise<void> => {
  const response = await fetchAPI(`projects/${projectId}/`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to update the project',
      await errorCauses(response),
    );
  }
};

type UseUpdateProjectOptions = UseMutationOptions<
  void,
  APIError,
  UpdateProjectProps
>;

export const useUpdateProject = (options?: UseUpdateProjectOptions) => {
  const queryClient = useQueryClient();
  return useMutation<void, APIError, UpdateProjectProps>({
    mutationFn: updateProject,
    ...options,
    onSuccess: (data, variables, context) => {
      void queryClient.invalidateQueries({
        queryKey: [KEY_LIST_PROJECT],
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
