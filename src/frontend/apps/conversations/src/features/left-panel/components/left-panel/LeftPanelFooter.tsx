import { Suspense, lazy } from 'react';
import { css } from 'styled-components';

import { Box } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { LaGaufre } from '@/features/header/components/LaGaufre';
import { OnboardingButton } from '@/features/onboarding';

import { LEFT_PANEL_FOOTER_HEIGHT_PX } from './conf';

const UserInfo = lazy(() =>
  import('@/features/auth/components/UserInfo').then((mod) => ({
    default: mod.UserInfo,
  })),
);

export const LeftPanelFooter = () => {
  const { spacingsTokens, componentTokens } = useCunninghamTheme();
  const showLaGaufre =
    (componentTokens as Record<string, unknown>)['la-gaufre'] === true;

  return (
    <Box
      data-testid="left-panel-footer"
      $justify="space-between"
      $align="center"
      $direction="row"
      $padding={{ horizontal: 'sm' }}
      $gap={spacingsTokens['sm']}
      $css={css`
        height: ${LEFT_PANEL_FOOTER_HEIGHT_PX}px;
        width: 100%;
        flex: 0 0 auto;
        border-top: 1px solid var(--c--contextuals--border--surface--primary);
      `}
    >
      <Box $direction="row" $gap={spacingsTokens.sm} $align="center">
        <Suspense fallback={null}>
          <UserInfo />
        </Suspense>
        {showLaGaufre && <LaGaufre />}
      </Box>
      <Box $direction="row" $gap={spacingsTokens['sm']} $align="center">
        <OnboardingButton />
      </Box>
    </Box>
  );
};
