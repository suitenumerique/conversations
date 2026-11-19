import { useEffect } from 'react';
import { createGlobalStyle, css } from 'styled-components';

import { Box } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { useResponsiveStore } from '@/stores';

import { LeftPanelContent } from './LeftPanelContent';
import { LeftPanelFooter } from './LeftPanelFooter';
import { LeftPanelHeader } from './LeftPanelHeader';

const MobileLeftPanelStyle = createGlobalStyle`
  body {
    overflow: hidden;
  }
`;

export const LeftPanel = () => {
  const { isDesktop } = useResponsiveStore();

  const { setPanelOpen, isPanelOpen } = useChatPreferencesStore();

  useEffect(() => {
    setPanelOpen(isDesktop ? true : false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDesktop]);

  return (
    <>
      {isDesktop && (
        <Box
          data-testid="left-panel-desktop"
          $css={`
            height: 100vh;
            width: 300px;
            min-width: 300px;
            overflow: hidden;
            border-right: 1px solid var(--c--contextuals--border--surface--primary);
            background-color: var(--c--contextuals--background--surface--tertiary);
          `}
          className="--docs--left-panel-desktop"
        >
          <Box
            $css={css`
              flex: 0 0 auto;
            `}
          >
            <LeftPanelHeader />
          </Box>
          <LeftPanelContent />
          <LeftPanelFooter />
        </Box>
      )}

      {!isDesktop && (
        <>
          {isPanelOpen && <MobileLeftPanelStyle />}
          <Box
            $hasTransition
            $css={css`
              z-index: 1000;
              overflow: visible;
              width: ${isPanelOpen ? '100%' : '200px'};
              width: 100vw;
              border-right: 1px solid
                var(--c--contextuals--border--surface-primary);
              position: absolute;
              top: 0px;
              left: ${isPanelOpen ? '0' : '-300px'};
              background-color: var(
                --c--contextuals--background--surface--secondary
              );
            `}
            className="--docs--left-panel-mobile"
          >
            <Box
              data-testid="left-panel-mobile"
              $css={css`
                display: ${isPanelOpen ? 'flex' : 'none'};
                flex-direction: column;
                width: 100%;
                height: 100vh;
                justify-content: center;
                align-items: center;
              `}
            >
              <LeftPanelHeader />
              <LeftPanelContent />
              <LeftPanelFooter />
            </Box>
          </Box>
        </>
      )}
    </>
  );
};
