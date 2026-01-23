import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box } from '@/components';
import { productName as _productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { Footer } from '@/features/footer';
import { LeftPanel } from '@/features/left-panel';
import { useResponsiveStore } from '@/stores';

import HomeBanner from './HomeBanner';
import { HomeHeader, getHeaderHeight } from './HomeHeader';

export function HomeContent() {
  const { t: _t } = useTranslation();
  const { colorsTokens: _colorsTokens } = useCunninghamTheme();
  const {
    isMobile: _isMobile,
    isSmallMobile,
    isTablet: _isTablet,
  } = useResponsiveStore();

  return (
    <Box as="main" className="--docs--home-content">
      <HomeHeader />
      {isSmallMobile && (
        <Box $css="& .--docs--left-panel-header{display: none;}">
          <LeftPanel />
        </Box>
      )}
      <Box
        $css={css`
          height: calc(100vh - ${getHeaderHeight(isSmallMobile)}px);
          overflow-y: auto;
        `}
      >
        <Box
          $align="center"
          $justify="center"
          $maxWidth="1120px"
          $padding={{ horizontal: isSmallMobile ? '1rem' : '3rem' }}
          $width="100%"
          $margin="auto"
        >
          <HomeBanner />
        </Box>
        <Footer />
      </Box>
    </Box>
  );
}
