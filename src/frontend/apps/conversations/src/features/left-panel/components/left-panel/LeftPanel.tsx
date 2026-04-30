import dynamic from 'next/dynamic';
import { useEffect } from 'react';
import { createGlobalStyle, css } from 'styled-components';

import { Box, SeparatedSection } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { LaGaufre } from '@/features/header/components/LaGaufre';
import { OnboardingButton } from '@/features/onboarding';
import { SettingsButton } from '@/features/settings';
import { useResponsiveStore } from '@/stores';

import { LeftPanelContent } from './LeftPanelContent';
import { LeftPanelHeader } from './LeftPanelHeader';

const MobileLeftPanelStyle = createGlobalStyle`
  body {
    overflow: hidden;
  }
`;

const UserInfo = dynamic(
  () =>
    import('@/features/auth/components/UserInfo').then((mod) => mod.UserInfo),
  { ssr: false },
);

export const LeftPanel = () => {
  const { isDesktop } = useResponsiveStore();

  const { spacingsTokens, componentTokens } = useCunninghamTheme();
  const showLaGaufre =
    (componentTokens as Record<string, unknown>)['la-gaufre'] === true;
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
          <SeparatedSection showSeparator={true} />
          <Box
            $padding={{ all: 'sm' }}
            $direction="row"
            $gap={spacingsTokens.xxs}
          >
            <OnboardingButton />
            <SettingsButton />
          </Box>
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
              <SeparatedSection showSeparator={false}></SeparatedSection>
              <Box
                $css={css`
                  display: flex;
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
                <Box $direction="row" $gap={spacingsTokens.sm} $align="center">
                  <OnboardingButton />
                  <SettingsButton />
                </Box>
                <Box
                  $direction="row"
                  $gap={spacingsTokens['sm']}
                  $align="center"
                >
                  {showLaGaufre && <LaGaufre />}
                  <UserInfo />
                </Box>
              </Box>
            </Box>
          </Box>
        </>
      )}
    </>
  );
};
