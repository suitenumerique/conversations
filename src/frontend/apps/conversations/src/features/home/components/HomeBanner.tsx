import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import IconAssistant from '@/assets/logo/logomark.svg';
import { Box, Icon, Text } from '@/components';
import { productName, useConfig } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { gotoLogin } from '@/features/auth';
import { useResponsiveStore } from '@/stores';

import BannerDarkMode from '../assets/banner-dark.svg';
import Banner from '../assets/banner.svg';

import { getHeaderHeight } from './HomeHeader';

export default function HomeBanner() {
  const { t } = useTranslation();
  const { theme, spacingsTokens, colorsTokens, componentTokens } =
    useCunninghamTheme();
  const { isMobile, isSmallMobile } = useResponsiveStore();
  const withProConnect = Boolean(
    (componentTokens as Record<string, unknown>)['home-proconnect'],
  );
  const { data: config } = useConfig();
  const documentationUrl = config?.FRONTEND_DOCUMENTATION_URL;

  return (
    <Box
      $maxWidth="78rem"
      $width="100%"
      $justify="space-around"
      $align="center"
      $height="100vh"
      $margin={{ top: `-${getHeaderHeight(isSmallMobile)}px` }}
      $position="relative"
      className="--docs--home-banner"
    >
      <Box
        $width="100%"
        $justify="center"
        $align="center"
        $position="relative"
        $direction={!isMobile ? 'row' : 'column'}
        $gap="1rem"
        $overflow="auto"
      >
        <Box
          $width={!isMobile ? '50%' : '100%'}
          $maxWidth="450px"
          $justify="center"
          $align="left"
          $gap={spacingsTokens['s']}
        >
          <IconAssistant
            aria-label={t('{{productName}} Logo', { productName })}
            width={64}
            color={colorsTokens['logo-1-light']}
          />
          <Text
            as="h2"
            $size="xs-alt"
            $theme="neutral"
            $variation="primary"
            $weight="bold"
            $textAlign="left"
            $margin="none"
            $css={css`
              line-height: 1.2;
            `}
          >
            {t('Your sovereign AI assistant')}
          </Text>
          <Text $theme="neutral" $variation="tertiary">
            {t(
              'A privacy-first assistant built for French public teams. Natively synced with LaSuite apps to help you draft, search, and decide without leaving your workflow.',
            )}
          </Text>

          <Box $direction={isMobile ? 'column' : 'row'} $gap="0.5rem">
            {withProConnect ? (
              // <ProConnectButton />
              <Button
                fullWidth={isMobile ? true : false}
                onClick={() => gotoLogin()}
              >
                {t('Login')}
              </Button>
            ) : (
              <Button
                onClick={() => gotoLogin()}
                icon={<Icon iconName="bolt" $color="white" />}
              >
                {t('Start conversation')}
              </Button>
            )}

            {documentationUrl ? (
              <Button
                fullWidth={isMobile ? true : false}
                href={documentationUrl}
                color="brand"
                variant="bordered"
                target="_blank"
              >
                {t('Know more')}
              </Button>
            ) : null}
          </Box>
        </Box>
        {!isMobile &&
          (theme.includes('dark') ? <BannerDarkMode /> : <Banner />)}
      </Box>
    </Box>
  );
}
