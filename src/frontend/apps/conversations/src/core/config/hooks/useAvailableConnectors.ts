import { useMemo } from 'react';

import { useAnalytics } from '@/libs';

import { useConfig } from '../api';
import { ConnectorConfig } from '../api/useConfig';

import { isFeatureFlagEnabled } from './useFeatureEnabled';

const NO_CONNECTORS: ConnectorConfig[] = [];

/**
 * The connectors the deployment offers this user: every connector from the
 * config whose feature flag, if it has one, is on for them. The backend
 * checks the same gates again on every turn; this only decides what to show.
 */
export const useAvailableConnectors = (): ConnectorConfig[] => {
  const { data: conf } = useConfig();
  const { isFeatureFlagActivated } = useAnalytics();

  return useMemo(() => {
    const connectors = conf?.CONNECTORS ?? NO_CONNECTORS;
    const available = connectors.filter(
      (connector) =>
        !connector.feature_flag ||
        isFeatureFlagEnabled(
          conf,
          connector.feature_flag,
          isFeatureFlagActivated,
        ),
    );
    return available.length ? available : NO_CONNECTORS;
  }, [conf, isFeatureFlagActivated]);
};
