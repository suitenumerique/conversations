import { useMemo } from 'react';

import { useAnalytics } from '@/libs';

import { useConfig } from '../api';
import { FeatureFlagState } from '../api/useConfig';

export const useFeatureEnabled = (featureKey: string): boolean => {
  const { data: conf } = useConfig();
  const { isFeatureFlagActivated } = useAnalytics();

  return useMemo(() => {
    const value = conf?.FEATURE_FLAGS?.[featureKey];
    if (value === FeatureFlagState.ENABLED) {
      return true;
    }
    if (!value || value === FeatureFlagState.DISABLED) {
      return false;
    }
    return isFeatureFlagActivated(featureKey);
  }, [conf, featureKey, isFeatureFlagActivated]);
};
