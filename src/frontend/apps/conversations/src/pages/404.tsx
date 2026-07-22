import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';

import Icon404 from '@/assets/icons/icon-404.svg';
import { Box, Icon, StyledLink, Text } from '@/components';
import { productName } from '@/core';

const StyledButton = styled(Button)`
  width: fit-content;
`;

const Page = () => {
  const { t } = useTranslation();

  return (
    <>
      <title>{`${t('Page Not Found - Error 404')} - ${productName}`}</title>
      <meta
        property="og:title"
        content={`${t('Page Not Found - Error 404')} - ${productName}`}
      />
      <Box
        $align="center"
        $margin="auto"
        $gap="1rem"
        $padding={{ bottom: '2rem' }}
      >
        <Icon404
          className="c__image-system-filter"
          aria-hidden
          style={{
            maxWidth: '100%',
            height: 'auto',
          }}
        />

        <Box $align="center" $gap="0.8rem">
          <Text as="p" $textAlign="center" $maxWidth="350px" $theme="primary">
            {t(
              'It seems that the page you are looking for does not exist or cannot be displayed correctly.',
            )}
          </Text>

          <StyledLink href="/">
            <StyledButton icon={<Icon iconName="house" $color="white" />}>
              {t('Home')}
            </StyledButton>
          </StyledLink>
        </Box>
      </Box>
    </>
  );
};

export default Page;
