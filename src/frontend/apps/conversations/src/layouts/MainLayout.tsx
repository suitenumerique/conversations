import { PropsWithChildren, useEffect, useState } from 'react';
import { css } from 'styled-components';

import { Box } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { Header } from '@/features/header';
import { LeftPanel } from '@/features/left-panel';
import { MAIN_LAYOUT_ID } from '@/layouts/conf';
import { useResponsiveStore } from '@/stores';
import { useElementHeight } from '@/hook/useElementHeight';
import { FeatureFlagState, useConfig } from '@/core';

type MainLayoutProps = {
  backgroundColor?: 'white' | 'grey';
};

const Banner = ({
  title = '',
  content = '',
}: {
  title?: string;
  content?: string;
}) => {
  if (!content) {
    return null;
  }
  return (
    <Box
      $css={css`
        background-color: #ccc;
          display: flex;
          align-items: center;
      `}
    >
        <strong>{title}</strong>
      <p>{content}</p>
    </Box>
  );
};

export function MainLayout({
  children,
  backgroundColor: _backgroundColor = 'white',
}: PropsWithChildren<MainLayoutProps>) {
  const { isDesktop } = useResponsiveStore();
  const { colorsTokens } = useCunninghamTheme();
  const { isPanelOpen } = useChatPreferencesStore();

  const [banners, setBanners] = useState({});
  const { data: conf } = useConfig();

  const [bannerRef, bannerHeight] = useElementHeight<HTMLDivElement>();

  useEffect(() => {
    setBanners(conf?.banners ?? {});
  }, [conf]);

  const HEADER_HEIGHT = `${isDesktop ? '65' : '52'}`;
  console.log(banners);
  console.log(bannerHeight);
  return (
    <Box className="--docs--main-layout">
      <Box
        ref={bannerRef}
        $css={css`
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 1001;
          background-color: #ccc;
        `}
      >
        <Banner content={banners?.environment?.content}></Banner>
        <Banner content={banners?.status?.content}></Banner>
      </Box>

      <Box
        $css={css`
          z-index: 1000;
          transition: left 0.3s ease;
          position: fixed;
          top: ${bannerHeight}px;
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
          top: ${bannerHeight}px;
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
