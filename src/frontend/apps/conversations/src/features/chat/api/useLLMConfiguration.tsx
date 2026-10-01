import { UseQueryOptions, useQuery } from '@tanstack/react-query';

import { APIError, fetchAPI } from '@/api';
import { TierSlug } from '@/features/chat/types';

export interface LLMModel {
  hrid: string;
  human_readable_name: string;
  icon: string;
  is_default: boolean;
  model_name: string;
  is_active?: boolean;
}

/** One entry of the compose-box tier selector. */
export interface LLMTier {
  slug: TierSlug;
  /** i18n key of the label, e.g. `router.tier.auto`. */
  label_key: string;
  recommended?: boolean;
  /** Ordinal leaves (1 to 3); absent on `auto`. */
  leaves?: number;
}

export interface LLMConfigurationResponse {
  models: LLMModel[];
  /**
   * Router tiers, only returned when the `router` feature flag is on: the tier
   * selector then replaces the model selector.
   */
  tiers?: LLMTier[];
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
