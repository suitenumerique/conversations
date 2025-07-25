import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { createGlobalStyle, css } from 'styled-components';

import { Box, SeparatedSection } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ButtonLogin } from '@/features/auth';
import { LanguagePicker } from '@/features/language';
import { useResponsiveStore } from '@/stores';

import { useLeftPanelStore } from '../stores';

import { LeftPanelContent } from './LeftPanelContent';
import { LeftPanelHeader } from './LeftPanelHeader';

const MobileLeftPanelStyle = createGlobalStyle`
  body {
    overflow: hidden;
  }
`;

export const LeftPanel = () => {
  const { isDesktop } = useResponsiveStore();

  const { colorsTokens, spacingsTokens } = useCunninghamTheme();
  const { togglePanel, isPanelOpen } = useLeftPanelStore();

  const pathname = usePathname();

  useEffect(() => {
    togglePanel(false);
  }, [pathname, togglePanel]);

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
            border-right: 1px solid ${colorsTokens['greyscale-200']};
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
        </Box>
      )}

      {!isDesktop && (
        <>
          {isPanelOpen && <MobileLeftPanelStyle />}
          <Box
            $hasTransition
            $css={css`
              z-index: 999;
              overflow: hidden;
              width: ${isPanelOpen ? '100%' : '200px'};
              height: calc(100dvh - 52px);
              border-right: 1px solid var(--c--theme--colors--greyscale-200);
              position: fixed;
              top: 52px;
              left: ${isPanelOpen ? '0' : '-300px'};
              background-color: var(--c--theme--colors--greyscale-000);
            `}
            className="--docs--left-panel-mobile"
          >
            <Box
              data-testid="left-panel-mobile"
              $css={css`
                width: 100%;
                justify-content: center;
                align-items: center;
                gap: ${spacingsTokens['base']};
              `}
            >
              <LeftPanelHeader />
              <LeftPanelContent />
              <SeparatedSection showSeparator={false}>
                <Box
                  $justify="center"
                  $align="center"
                  $gap={spacingsTokens['sm']}
                >
                  <ButtonLogin />
                  <LanguagePicker />
                </Box>
              </SeparatedSection>
            </Box>
          </Box>
        </>
      )}
    </>
  );
};
