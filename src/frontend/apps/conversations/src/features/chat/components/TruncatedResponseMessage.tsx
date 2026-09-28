import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';

export const TruncatedResponseMessage = () => {
  const { t } = useTranslation();

  return (
    <Box
      $direction="column"
      $gap="6px"
      $width="100%"
      $maxWidth="var(--chat-content-max-width, 750px)"
      $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
      $padding={{ left: '13px' }}
    >
      <Text $variation="550" $theme="greyscale" $weight="700">
        {t(
          'This response reached its maximum length. Rephrase your question to be more specific.',
        )}
      </Text>
    </Box>
  );
};
