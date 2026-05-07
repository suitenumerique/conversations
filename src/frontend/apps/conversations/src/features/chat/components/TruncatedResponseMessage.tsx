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
      <Text $variation="550" $theme="greyscale">
        {t(
          'The response was cut off because it reached the maximum length. Try rephrasing your question to get a shorter answer.',
        )}
      </Text>
    </Box>
  );
};
