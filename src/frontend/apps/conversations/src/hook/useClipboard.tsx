import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components';

export const useClipboard = () => {
  const { showToast } = useToast();
  const { t } = useTranslation();

  return useCallback(
    (text: string, successMessage?: string, errorMessage?: string) => {
      navigator.clipboard
        .writeText(text)
        .then(() => {
          showToast(
            'success',
            successMessage ?? t('Copied'),
            'content_copy',
            3000,
          );
        })
        .catch(() => {
          showToast(
            'error',
            errorMessage ?? t('Failed to copy'),
            'content_copy',
            3000,
          );
        });
    },
    [t, showToast],
  );
};
