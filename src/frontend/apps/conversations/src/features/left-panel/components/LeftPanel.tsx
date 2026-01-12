import { useEffect } from 'react';
import { createGlobalStyle, css } from 'styled-components';

import { Box, SeparatedSection } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ButtonLogin } from '@/features/auth';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { LanguagePicker } from '@/features/language';
import { SettingsButton } from '@/features/settings';
import { useResponsiveStore } from '@/stores';

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
        </Box>
      )}

      {!isDesktop && (
        <>
          {isPanelOpen && <MobileLeftPanelStyle />}
          <Box
            $hasTransition
            $css={css`
              z-index: 1000;
              overflow: hidden;
              width: ${isPanelOpen ? '100%' : '200px'};
              height: calc(100dvh - 52px);
              border-right: 1px solid
                var(--c--contextuals--border--surface-primary);
              position: fixed;
              top: 52px;
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
                width: 100%;
                justify-content: center;
                align-items: center;
                gap: ${spacingsTokens['base']};
              `}
            >
              <LeftPanelContent />
              <SeparatedSection showSeparator={false}>
                <Box
                  $css={css`
                    display: flex;
                    position: absolute;
                    bottom: 0;
                    height: 52px;
                    width: 100%;
                    gap: ${spacingsTokens['base']};
                    border-top: 1px solid
                      var(--c--contextuals--border--surface--primary);
                  `}
                  $justify="space-between"
                  $align="center"
                  $direction="row"
                  $padding={{ horizontal: 'sm' }}
                  $gap={spacingsTokens['sm']}
                >
                  <ButtonLogin />
                  <Box
                    $direction="row"
                    $gap={spacingsTokens['sm']}
                    $align="center"
                  >
                    <LanguagePicker />
                    <SettingsButton />
                  </Box>
                </Box>
              </SeparatedSection>
            </Box>
          </Box>
        </>
      )}
    </>
  );
};
