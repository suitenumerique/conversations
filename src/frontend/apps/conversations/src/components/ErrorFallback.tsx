import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';

import { Box } from './Box';
import { Icon } from './Icon';
import { Text } from './Text';

const StyledButton = styled(Button)`
  width: fit-content;
`;

/**
 * Shown by the top-level error boundary instead of a blank page, for example
 * when a chunk of a previous release cannot be loaded any more.
 */
export const ErrorFallback = () => {
  const { t } = useTranslation();

  return (
    <Box $align="center" $margin="auto" $gap="0.8rem" $padding="2rem">
      <Text as="p" $textAlign="center" $maxWidth="350px" $theme="primary">
        {t(
          'An error occurred while displaying the page. Reloading it usually fixes the problem.',
        )}
      </Text>

      <StyledButton
        icon={<Icon iconName="refresh" $color="white" />}
        onClick={() => window.location.reload()}
      >
        {t('Reload the page')}
      </StyledButton>
    </Box>
  );
};
