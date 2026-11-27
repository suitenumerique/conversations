import { useCallback } from 'react';

import { useAnalytics } from '@/libs';

import { useChatPreferencesStore } from '../stores/useChatPreferencesStore';

/**
 * Switch a connector's chat-box force on or off, and report it.
 *
 * The force is client-side state the backend only sees on the next message,
 * so the toggle itself is captured here (`connector_force_toggled`); the
 * forced turn is captured by the backend (`connector_forced`).
 */
export const useToggleForceConnector = () => {
  const { trackEvent } = useAnalytics();

  return useCallback(
    (slug: string) => {
      const { forcedConnectors, toggleForceConnector } =
        useChatPreferencesStore.getState();
      const enabled = !forcedConnectors.includes(slug);
      toggleForceConnector(slug);
      trackEvent({
        eventName: 'connector_force_toggled',
        properties: { connector_id: slug, enabled },
      });
    },
    [trackEvent],
  );
};
