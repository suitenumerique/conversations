import { useMemo } from 'react';

import { useAnalytics } from '@/libs';

import { useConfig } from '../api';
import { ConfigResponse, FeatureFlagState } from '../api/useConfig';

/**
 * Whether a feature flag is on, given the config and the analytics provider
 * that resolves dynamic flags. Shared by `useFeatureEnabled` and the hooks that
 * resolve several flags at once.
 */
export const isFeatureFlagEnabled = (
  conf: ConfigResponse | undefined,
  featureKey: string,
  isFeatureFlagActivated: (flagName: string) => boolean,
): boolean => {
  const value = conf?.FEATURE_FLAGS?.[featureKey];
  if (value === FeatureFlagState.ENABLED) {
    return true;
  }
  if (!value || value === FeatureFlagState.DISABLED) {
    return false;
  }
  return isFeatureFlagActivated(featureKey);
};

export const useFeatureEnabled = (featureKey: string): boolean => {
  const { data: conf } = useConfig();
  const { isFeatureFlagActivated } = useAnalytics();

  return useMemo(
    () => isFeatureFlagEnabled(conf, featureKey, isFeatureFlagActivated),
    [conf, featureKey, isFeatureFlagActivated],
  );
};
