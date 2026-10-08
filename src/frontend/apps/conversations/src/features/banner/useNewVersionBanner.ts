import { useTranslation } from 'react-i18next';

import { INITIAL_DATA_UPDATED_AT, useConfig } from '@/core/config';

import packageJson from '../../../package.json';

import { BannerProps } from './Banner';

/**
 * Warn a tab still running the bundle of a previous release: until it reloads,
 * it keeps calling an API that may have changed under it. Backend and frontend
 * are released with the same version number.
 */
export const useNewVersionBanner = (): BannerProps | undefined => {
  const { t } = useTranslation();
  const { data: config, dataUpdatedAt } = useConfig();

  // The config stored by a previous visit may carry a previous release: only
  // trust one fetched since this page loaded.
  const isFetched = dataUpdatedAt > INITIAL_DATA_UPDATED_AT;

  if (
    !isFetched ||
    !config?.RELEASE ||
    config.RELEASE === packageJson.version
  ) {
    return undefined;
  }

  return {
    level: 'warning',
    title: t('A new version is available, reload to avoid errors.'),
    content: '',
    action: {
      label: t('Reload'),
      onClick: () => window.location.reload(),
    },
  };
};
