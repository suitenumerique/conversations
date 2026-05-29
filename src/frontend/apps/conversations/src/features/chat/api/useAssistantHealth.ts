import { useQuery } from '@tanstack/react-query';

import { fetchAPI } from '@/api';
import { StatusBanner } from '@/core/config/api/useConfig';

export interface AssistantHealthResponse {
  banners: StatusBanner[];
  blocked: boolean;
}

const FALLBACK: AssistantHealthResponse = { banners: [], blocked: false };

const getAssistantHealth = async (): Promise<AssistantHealthResponse> => {
  try {
    const response = await fetchAPI('assistant-health/');
    if (!response.ok) {
      return FALLBACK;
    }
    return response.json() as Promise<AssistantHealthResponse>;
  } catch {
    return FALLBACK;
  }
};

export const KEY_ASSISTANT_HEALTH = 'assistant-health';

export function useAssistantHealth() {
  return useQuery<AssistantHealthResponse>({
    queryKey: [KEY_ASSISTANT_HEALTH],
    queryFn: getAssistantHealth,
    refetchInterval: 60_000,
  });
}
