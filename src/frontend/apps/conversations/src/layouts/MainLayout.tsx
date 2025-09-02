import { PropsWithChildren } from 'react';
import { css } from 'styled-components';

import { Box } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { Header } from '@/features/header';
import { LeftPanel } from '@/features/left-panel';
import { useLeftPanelStore } from '@/features/left-panel/stores';
import { MAIN_LAYOUT_ID } from '@/layouts/conf';
import { useResponsiveStore } from '@/stores';

type MainLayoutProps = {
  backgroundColor?: 'white' | 'grey';
};

export function MainLayout({
  children,
  backgroundColor: _backgroundColor = 'white',
}: PropsWithChildren<MainLayoutProps>) {
  const { isDesktop } = useResponsiveStore();
  const { colorsTokens } = useCunninghamTheme();
  const { togglePanel: _togglePanel, isPanelOpen } = useLeftPanelStore();

  const HEADER_HEIGHT = `${isDesktop ? '65' : '52'}`;

  return (
    <Box className="--docs--main-layout">
      <Box
        $css={css`
          z-index: 1000;
          transition: left 0.3s ease;
          position: fixed;
          width: 300px;
          left: ${isPanelOpen ? '0px' : '-300px'};
        `}
      >
        <LeftPanel />
      </Box>
      <Box
        $css={css`
          transition: all 0.3s ease;
          position: fixed;
          left: ${isDesktop && isPanelOpen ? '300px' : '0px'};
          width: calc(100vw - ${isDesktop && isPanelOpen ? '300px' : '0px'});
        `}
      >
        <Header />
        <Box $direction="row" $width="100%">
          <Box
            as="main"
            id={MAIN_LAYOUT_ID}
            $align="center"
            $width="100vw"
            $height={`calc(100dvh - ${HEADER_HEIGHT}px)`}
            $padding={{
              all: isDesktop ? '0' : '0',
            }}
            $background={colorsTokens['greyscale-000']}
            $css={css`
              overflow-y: auto;
              overflow-x: clip;
            `}
          >
            {children}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
