import { UseQueryOptions, useQuery } from '@tanstack/react-query';

import { APIError, fetchAPI } from '@/api';

export interface LLMModel {
  hrid: string;
  human_readable_name: string;
  icon: string;
  is_default: boolean;
  model_name: string;
}

export interface LLMConfigurationResponse {
  models: LLMModel[];
}

export const KEY_LLM_CONFIGURATION = 'llm-configuration';

const getLLMConfiguration = async (): Promise<LLMConfigurationResponse> => {
  const response = await fetchAPI('llm-configuration/');

  if (!response.ok) {
    throw new APIError('Failed to fetch LLM configuration', {
      status: response.status,
    });
  }

  return response.json() as Promise<LLMConfigurationResponse>;
};

export function useLLMConfiguration(
  queryConfig?: UseQueryOptions<
    LLMConfigurationResponse,
    APIError,
    LLMConfigurationResponse
  >,
) {
  return useQuery<LLMConfigurationResponse, APIError, LLMConfigurationResponse>(
    {
      queryKey: [KEY_LLM_CONFIGURATION],
      queryFn: getLLMConfiguration,
      ...queryConfig,
    },
  );
}
