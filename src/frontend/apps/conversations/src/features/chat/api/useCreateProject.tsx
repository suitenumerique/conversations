import {
  UseMutationOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { ChatProject } from '@/features/chat/types';

import { KEY_LIST_PROJECT } from './useProjects';

interface CreateProjectProps {
  title: string;
  icon: string;
  color: string;
  llm_instructions?: string;
}

export const createProject = async (
  props: CreateProjectProps,
): Promise<ChatProject> => {
  const response = await fetchAPI('projects/', {
    method: 'POST',
    body: JSON.stringify(props),
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to create the project',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<ChatProject>;
};

type UseCreateProjectOptions = UseMutationOptions<
  ChatProject,
  APIError,
  CreateProjectProps
>;

export const useCreateProject = (options?: UseCreateProjectOptions) => {
  const queryClient = useQueryClient();
  return useMutation<ChatProject, APIError, CreateProjectProps>({
    mutationFn: createProject,
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
