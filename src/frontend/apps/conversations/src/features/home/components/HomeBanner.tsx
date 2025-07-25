import { Button } from '@openfun/cunningham-react';
import _Image from 'next/image';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import IconAssistant from '@/assets/logo/assistant.svg';
import { Box, Icon, Text } from '@/components';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { ProConnectButton, gotoLogin } from '@/features/auth';
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
          $maxWidth="400px"
          $justify="center"
          $align="center"
          $gap={spacingsTokens['md']}
        >
          <IconAssistant
            aria-label={t('{{productName}} Logo', { productName })}
            width={64}
            color={colorsTokens['primary-text']}
          />
          <Text
            as="h2"
            $size={!isMobile ? 'xs-alt' : '2.3rem'}
            $variation="800"
            $weight="bold"
            $textAlign="center"
            $margin="none"
            $css={css`
              line-height: ${!isMobile ? '56px' : '45px'};
            `}
          >
            {t('Your digital assistant')}
          </Text>
          <Text
            $padding={{ horizontal: 'base' }}
            $size="lg"
            $variation="700"
            $textAlign="center"
          >
            {t(
              'Ask questions, get help with writing, or find reliable information online — Assistant simplifies your work while keeping your data secure.',
            )}
          </Text>
          {withProConnect ? (
            <ProConnectButton />
          ) : (
            <Button
              onClick={() => gotoLogin()}
              icon={<Icon iconName="bolt" $color="white" />}
            >
              {t('Start conversation')}
            </Button>
          )}
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
