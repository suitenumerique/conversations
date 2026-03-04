import {
  UseMutationOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

import { KEY_LIST_PROJECT } from './useProjects';

interface RemoveProjectProps {
  projectId: string;
}

export const removeProject = async ({
  projectId,
}: RemoveProjectProps): Promise<void> => {
  const response = await fetchAPI(`projects/${projectId}/`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to delete the project',
      await errorCauses(response),
    );
  }
};

type UseRemoveProjectOptions = UseMutationOptions<
  void,
  APIError,
  RemoveProjectProps
>;

export const useRemoveProject = (options?: UseRemoveProjectOptions) => {
  const queryClient = useQueryClient();
  return useMutation<void, APIError, RemoveProjectProps>({
    mutationFn: removeProject,
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
