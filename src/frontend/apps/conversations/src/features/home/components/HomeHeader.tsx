import Image from 'next/image';
import { useTranslation } from 'react-i18next';

import Logo from '@/assets/logo/logo-assistant.svg';
import { Box } from '@/components';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { ButtonLogin } from '@/features/auth/components/ButtonLogin';
import { Feedback } from '@/features/feedback/Feedback';
import { LaGaufre } from '@/features/header/components/LaGaufre';
import { LanguagePicker } from '@/features/language';
import { useResponsiveStore } from '@/stores';

export const HEADER_HEIGHT = 91;
export const HEADER_HEIGHT_MOBILE = 52;

export const getHeaderHeight = (isSmallMobile: boolean) =>
  isSmallMobile ? HEADER_HEIGHT_MOBILE : HEADER_HEIGHT;

export const HomeHeader = () => {
  const { t } = useTranslation();
  const { spacingsTokens, colorsTokens, componentTokens } =
    useCunninghamTheme();
  const { isSmallMobile, isDesktop } = useResponsiveStore();
  const logo = (componentTokens as Record<string, unknown>).logo as
    | { src: string; alt: string; widthHeader: string; widthFooter: string }
    | undefined;
  const showLaGaufre =
    (componentTokens as Record<string, unknown>)['la-gaufre'] === true;

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
            width={139}
            color={colorsTokens['logo-1-light']}
          />
        </Box>
        {isDesktop && <Feedback />}
      </Box>

      <Box $direction="row" $gap="1rem" $align="center">
        {!isSmallMobile && <ButtonLogin />}
        {!isSmallMobile && (
          <LanguagePicker color="brand" size="medium" compact={false} />
        )}
        {showLaGaufre && <LaGaufre />}
      </Box>
    </Box>
  );
};
