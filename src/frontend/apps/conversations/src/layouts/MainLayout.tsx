import { PropsWithChildren } from 'react';
import { css } from 'styled-components';

import { Box } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { Header } from '@/features/header';
import { LeftPanel } from '@/features/left-panel';
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
  const { isPanelOpen } = useChatPreferencesStore();

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
        $flex="none"
        className={
          isDesktop && !isPanelOpen
            ? 'main-layout__chat-column--wide'
            : undefined
        }
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
            $width="100dvw"
            $height="100dvh"
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
