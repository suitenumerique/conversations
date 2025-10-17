import { Button } from '@openfun/cunningham-react';
import _Image from 'next/image';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

// import IconAssistant from '@/assets/logo/assistant.svg';
import IconAssistant from '@/assets/logo/logo-beta.svg';
import { Box, Icon, Text } from '@/components';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { gotoLogin } from '@/features/auth';
// import { ProConnectButton } from '@/features/auth';
import { useResponsiveStore } from '@/stores';

import Banner from '../assets/banner.svg';

import { getHeaderHeight } from './HomeHeader';

export default function HomeBanner() {
  const { t } = useTranslation();
  const { componentTokens, spacingsTokens, colorsTokens } =
    useCunninghamTheme();
  const { isMobile, isSmallMobile } = useResponsiveStore();
  const withProConnect = componentTokens['home-proconnect'];

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
        $css="flex-basis: 70%;"
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
            color={colorsTokens['primary-text']}
          />
          <Text
            as="h2"
            $size="xs-alt"
            $variation="800"
            $weight="bold"
            $textAlign="left"
            $margin="none"
            $css={css`
              line-height: 1.2;
            `}
          >
            {t('Your sovereign AI assistant')}
          </Text>
          {/*          <Text
            // $padding={{ horizontal: 'base' }}
            $size="lg"
            $variation="700"
            $textAlign="left"
          >
            {t(
              'Ask questions, get help with writing, or find reliable information online — Assistant simplifies your work while keeping your data secure.',
            )}
          </Text>*/}
          <Text $variation="500">
            {t(
              'A privacy-first assistant built for French public teams. Natively synced with LaSuite apps to help you draft, search, and decide without leaving your workflow. Beta access is available with a referral code.',
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

            <Button
              fullWidth={isMobile ? true : false}
              href="https://docs.numerique.gouv.fr/docs/7a6e6475-5b8f-4ffb-95ea-198da9ebd6d0/"
              color="tertiary"
              target="_blank"
            >
              {t('Know more')}
            </Button>
          </Box>
        </Box>
        {!isMobile && <Banner />}
      </Box>
      {/*      <Box $css="bottom: 3rem" $position="absolute">
        <Button
          color="secondary"
          icon={
            <Icon $theme="primary" $variation="800" iconName="expand_more" />
          }
          onClick={(e) => {
            e.preventDefault();
            document
              .querySelector('#docs-app-info')
              ?.scrollIntoView({ behavior: 'smooth' });
          }}
        >
          {t('Show more')}
        </Button>
      </Box>*/}
    </Box>
  );
}
