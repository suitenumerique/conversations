import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

/**
 * One-line explanation shown above the very first routed answer a user sees
 *. The "seen" flag is persisted in
 * the chat preferences store, so the sentence never shows again — but it stays
 * on screen for the answer it was mounted with.
 */
export const RouterIntro = () => {
  const { t } = useTranslation();
  const { hasSeenRouterIntro, markRouterIntroSeen } = useChatPreferencesStore();
  // Captured once: marking the intro as seen below must not hide it mid-turn.
  const [show] = useState(() => !hasSeenRouterIntro);

  useEffect(() => {
    if (show) {
      markRouterIntroSeen();
    }
  }, [show, markRouterIntroSeen]);

  if (!show) {
    return null;
  }

  return (
    <Box $width="100%" $margin={{ bottom: 'xs' }} data-testid="router-intro">
      <Text $theme="neutral" $variation="tertiary" $size="sm">
        {t(
          'For each question, the assistant automatically picks the most suitable and most frugal model. You can see this choice under each answer.',
        )}
      </Text>
    </Box>
  );
};
