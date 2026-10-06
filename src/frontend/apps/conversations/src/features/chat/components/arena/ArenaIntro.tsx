import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

/**
 * One-line explanation shown above the very first arena split a user sees.
 * The "seen" flag is persisted in the chat preferences store, so the sentence
 * never shows again — but it stays on screen for the split it was mounted with.
 */
export const ArenaIntro = () => {
  const { t } = useTranslation();
  const { hasSeenArenaIntro, markArenaIntroSeen } = useChatPreferencesStore();
  // Captured once: marking the intro as seen below must not hide it mid-turn.
  const [show] = useState(() => !hasSeenArenaIntro);

  useEffect(() => {
    if (show) {
      markArenaIntroSeen();
    }
  }, [show, markArenaIntroSeen]);

  if (!show) {
    return null;
  }

  return (
    <Box
      $width="100%"
      $maxWidth="var(--chat-content-max-width, 750px)"
      $margin={{ all: 'auto', top: 'base', bottom: '0' }}
      $padding={{ left: '13px', right: '13px' }}
    >
      <Text $theme="neutral" $variation="tertiary" $size="sm">
        {t(
          'Two answers are shown. Choose the one you prefer, it will be kept in the conversation.',
        )}
      </Text>
    </Box>
  );
};
