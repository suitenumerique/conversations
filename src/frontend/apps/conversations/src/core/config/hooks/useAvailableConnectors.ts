import { useMemo } from 'react';

import { useAnalytics } from '@/libs';

import { ConnectorConfig, useConfig } from '../api/useConfig';

import { isFeatureFlagEnabled } from './useFeatureEnabled';

/**
 * The connectors this user may use, in declaration order: every connector the
 * deployment declares whose feature flag, if any, is on for them.
 *
 * Built from `/config/` alone, so a new connector needs no frontend release.
 */
export const useAvailableConnectors = (): ConnectorConfig[] => {
  const { data: conf } = useConfig();
  const { isFeatureFlagActivated } = useAnalytics();

  return useMemo(
    () =>
      (conf?.connectors ?? []).filter(
        (connector) =>
          !connector.feature_flag ||
          isFeatureFlagEnabled(
            conf,
            connector.feature_flag,
            isFeatureFlagActivated,
          ),
      ),
    [conf, isFeatureFlagActivated],
  );
};

/**
 * The connector's description in `language`: the exact code, then its base
 * language (`fr` for `fr-fr`), then English, then whichever text is given.
 */
export const connectorDescription = (
  connector: ConnectorConfig,
  language: string,
): string | undefined => {
  const texts = connector.description;
  if (!texts) {
    return undefined;
  }
  const code = language.toLowerCase();
  return (
    texts[code] ??
    texts[code.split('-')[0]] ??
    texts.en ??
    Object.values(texts)[0]
  );
};
