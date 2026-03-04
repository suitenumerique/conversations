import { UseQueryOptions, useQuery } from '@tanstack/react-query';

import {
  APIError,
  APIList,
  errorCauses,
  fetchAPI,
  useAPIInfiniteQuery,
} from '@/api';
import { ChatProject } from '@/features/chat/types';

const _projectsOrdering = [
  'title',
  '-title',
  'created_at',
  '-created_at',
  'updated_at',
  '-updated_at',
] as const;

export type ProjectsOrdering = (typeof _projectsOrdering)[number];

export type ProjectsParams = {
  page: number;
  ordering?: ProjectsOrdering;
  title?: string;
  page_size?: number;
};

export type ProjectsResponse = APIList<ChatProject>;

export const getProjects = async (
  params: ProjectsParams,
): Promise<ProjectsResponse> => {
  const searchParams = new URLSearchParams();
  if (params.page) {
    searchParams.set('page', params.page.toString());
  }

  if (params.ordering) {
    searchParams.set('ordering', params.ordering);
  }

  if (params.title) {
    searchParams.set('title', params.title);
  }

  if (params.page_size) {
    searchParams.set('page_size', params.page_size.toString());
  }

  const response = await fetchAPI(`projects/?${searchParams.toString()}`);

  if (!response.ok) {
    throw new APIError(
      'Failed to get the projects',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<ProjectsResponse>;
};

export const KEY_LIST_PROJECT = 'projects';

export function useProjects(
  param: ProjectsParams,
  queryConfig?: UseQueryOptions<ProjectsResponse, APIError, ProjectsResponse>,
) {
  return useQuery<ProjectsResponse, APIError, ProjectsResponse>({
    queryKey: [KEY_LIST_PROJECT, param],
    queryFn: () => getProjects(param),
    ...queryConfig,
  });
}

export const useInfiniteProjects = (params: ProjectsParams) => {
  return useAPIInfiniteQuery(KEY_LIST_PROJECT, getProjects, params);
};
