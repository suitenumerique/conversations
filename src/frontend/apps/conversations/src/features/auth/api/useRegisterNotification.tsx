import { useMutation } from '@tanstack/react-query';

import { APIError, errorCauses, fetchAPI } from '@/api';

export const registerNotification = async (): Promise<{ detail: string }> => {
  const response = await fetchAPI(`activation/register/`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new APIError(
      'Failed to register for notification',
      await errorCauses(response),
    );
  }

  return response.json() as Promise<{ detail: string }>;
};

export function useRegisterNotification() {
  return useMutation<{ detail: string }, APIError, void>({
    mutationFn: registerNotification,
  });
}
