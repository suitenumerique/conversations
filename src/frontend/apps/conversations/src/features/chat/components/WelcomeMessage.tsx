import { memo } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';

const WELCOME_PADDING = { all: 'base', bottom: 'md' } as const;
const WELCOME_MARGIN = {
  horizontal: 'base',
  bottom: 'md',
  top: '-105px',
} as const;
const WELCOME_TEXT_MARGIN = { all: '0' } as const;

export const WelcomeMessage = memo(() => {
  const { t } = useTranslation();

  return (
    <Box $padding={WELCOME_PADDING} $align="center" $margin={WELCOME_MARGIN}>
      <Text as="h2" $size="xl" $weight="600" $margin={WELCOME_TEXT_MARGIN}>
        {t('What is on your mind?')}
      </Text>
    </Box>
  );
});
WelcomeMessage.displayName = 'WelcomeMessage';
