import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import styled from 'styled-components';

import Icon404 from '@/assets/icons/icon-404.svg';
import { Box, Icon, StyledLink, Text } from '@/components';
import { productName } from '@/core';
import { useAuth } from '@/features/auth';

const StyledButton = styled(Button)`
  width: fit-content;
`;

const Page = () => {
  const { t } = useTranslation();
  const { authenticated } = useAuth();
  const navigate = useNavigate();

  // An authorized user should never see this page; send them to the app.
  useEffect(() => {
    if (authenticated) {
      void navigate('/', { replace: true });
    }
  }, [authenticated, navigate]);

  return (
    <>
      <title>{`${t('Access denied')} - ${productName}`}</title>
      <meta
        property="og:title"
        content={`${t('Access denied')} - ${productName}`}
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
          <Text
            as="h2"
            $textAlign="center"
            $maxWidth="420px"
            $theme="primary"
            $weight="bold"
          >
            {t('Access denied')}
          </Text>
          <Text as="p" $textAlign="center" $maxWidth="420px" $theme="primary">
            {t("Your account isn't authorized to use {{productName}}.", {
              productName,
            })}
          </Text>
          <Text as="p" $textAlign="center" $maxWidth="420px" $theme="primary">
            {t(
              'Access requires the appropriate role for your administration. If you think this is a mistake, contact your administrator.',
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
