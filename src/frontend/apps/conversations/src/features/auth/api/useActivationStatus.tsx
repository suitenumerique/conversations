import { useQuery } from '@tanstack/react-query';

import { APIError, fetchAPI } from '@/api';

export interface ActivationStatusResponse {
  is_activated: boolean;
  activation: {
    id: string;
    code: string;
    created_at: string;
    user: string;
  } | null;
  requires_activation: boolean;
}

export const KEY_ACTIVATION_STATUS = 'activation-status';

const getActivationStatus = async (): Promise<ActivationStatusResponse> => {
  const response = await fetchAPI('activation/status/');

  if (!response.ok) {
    throw new APIError('Failed to get activation status', {
      status: response.status,
    });
  }

  return response.json() as Promise<ActivationStatusResponse>;
};

export function useActivationStatus() {
  return useQuery<ActivationStatusResponse, APIError, ActivationStatusResponse>(
    {
      queryKey: [KEY_ACTIVATION_STATUS],
      queryFn: () => getActivationStatus(),
      retry: false, // Don't retry on auth errors
      staleTime: 1000 * 60 * 5, // 5 minutes
    },
  );
}
