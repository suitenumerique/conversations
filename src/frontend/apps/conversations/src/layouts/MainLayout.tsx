import { PropsWithChildren, useState } from 'react';
import { css } from 'styled-components';

import { Box } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { Header } from '@/features/header';
import { LeftPanel } from '@/features/left-panel';
import { SourcePanel } from '@/features/sources-panel';
import { MAIN_LAYOUT_ID } from '@/layouts/conf';
import { useResponsiveStore } from '@/stores';

const SOURCES_PANEL_WIDTH_PX = 360;

type MainLayoutProps = {
  backgroundColor?: 'white' | 'grey';
};

export function MainLayout({
  children,
  backgroundColor: _backgroundColor = 'white',
}: PropsWithChildren<MainLayoutProps>) {
  const { isDesktop } = useResponsiveStore();
  const { isPanelOpen, isSourcesPanelOpen } = useChatPreferencesStore();
  const [sourcesAnchorEl, setSourcesAnchorEl] = useState<HTMLDivElement | null>(
    null,
  );

  const leftPanelOffset = isDesktop && isPanelOpen ? 300 : 0;
  const sourcesPanelOffset =
    isDesktop && isSourcesPanelOpen ? SOURCES_PANEL_WIDTH_PX : 0;

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
      <SourcePanel anchor={sourcesAnchorEl}>
        <Box
          $flex="none"
          className={
            isDesktop && !isPanelOpen
              ? 'main-layout__chat-column--wide'
              : undefined
          }
          $css={css`
            transition: all 0.3s ease;
            position: fixed;
            left: ${leftPanelOffset}px;
            width: calc(100vw - ${leftPanelOffset}px - ${sourcesPanelOffset}px);
            min-height: 100dvh;
          `}
        >
          <Header />
          <Box $direction="row" $width="100%">
            <Box
              as="main"
              id={MAIN_LAYOUT_ID}
              $align="center"
              $width="100%"
              $height="100dvh"
              $css={css`
                overflow-y: auto;
                overflow-x: clip;
              `}
            >
              {children}
            </Box>
          </Box>
          <Box
            ref={setSourcesAnchorEl}
            aria-hidden={!isSourcesPanelOpen}
            className="main-layout__sources-panel-anchor"
            $css={css`
              ${isDesktop
                ? css`
                    position: fixed;
                    top: 0;
                    right: ${isSourcesPanelOpen ? '0px' : '-300px'};
                    bottom: 0;
                    z-index: 1001;
                    width: ${SOURCES_PANEL_WIDTH_PX}px;
                  `
                : css`
                    position: fixed;
                    inset: 0;
                    width: 100%;
                    z-index: 1002;
                  `}
              pointer-events: ${isSourcesPanelOpen ? 'auto' : 'none'};
              visibility: ${isSourcesPanelOpen ? 'visible' : 'hidden'};
              transition: right 0.3s ease;
            `}
          />
        </Box>
      </SourcePanel>
    </Box>
  );
}
