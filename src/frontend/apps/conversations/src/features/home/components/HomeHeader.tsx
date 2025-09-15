import Image from 'next/image';
import { useTranslation } from 'react-i18next';

import Logo from '@/assets/logo/logo-assistant.svg';
import { Box } from '@/components';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { ButtonLogin } from '@/features/auth';
import { Feedback } from '@/features/feedback/Feedback';
import { ButtonTogglePanel, Title as _Title } from '@/features/header/';
import { LaGaufre } from '@/features/header/components/LaGaufre';
import { LanguagePicker } from '@/features/language';
import { useResponsiveStore } from '@/stores';

export const HEADER_HEIGHT = 91;
export const HEADER_HEIGHT_MOBILE = 52;

export const getHeaderHeight = (isSmallMobile: boolean) =>
  isSmallMobile ? HEADER_HEIGHT_MOBILE : HEADER_HEIGHT;

export const HomeHeader = () => {
  const { t } = useTranslation();
  const { themeTokens, spacingsTokens, colorsTokens } = useCunninghamTheme();
  const logo = themeTokens.logo;
  const { isSmallMobile } = useResponsiveStore();

  return (
    <Box
      $direction="row"
      $justify="space-between"
      as="header"
      $align="center"
      $width="100%"
      $padding={{ horizontal: 'small' }}
      $height={`${isSmallMobile ? HEADER_HEIGHT_MOBILE : HEADER_HEIGHT}px`}
      className="--docs--home-header"
    >
      <Box
        $align="center"
        $gap="1.6rem"
        $direction="row"
        $width={isSmallMobile ? '100%' : 'auto'}
        $justify="center"
      >
        {isSmallMobile && (
          <Box $position="absolute" $css="left: 1rem;">
            <ButtonTogglePanel />
          </Box>
        )}
        {!isSmallMobile && logo?.src && (
          <Image
            priority
            src={logo.src}
            alt={logo.alt}
            width={0}
            height={0}
            style={{ width: logo.widthHeader, height: 'auto' }}
          />
        )}
        <Box
          $align="center"
          $gap={spacingsTokens['3xs']}
          $direction="row"
          $position="relative"
          $height="fit-content"
        >
          <Logo
            aria-label={t('{{productName}} Logo', { productName })}
            width={188}
            color={colorsTokens['primary-text']}
          />
        </Box>
        {!isSmallMobile && <Feedback />}
      </Box>
      {!isSmallMobile && (
        <Box $direction="row" $gap="1rem" $align="center">
          <ButtonLogin />
          <LanguagePicker />
          <LaGaufre />
        </Box>
      )}
    </Box>
  );
};
