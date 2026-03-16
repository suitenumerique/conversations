import { Box } from '@/components';
import { useAuth } from '@/features/auth/hooks';
import { LeftPanelConversations } from '@/features/left-panel/components/LeftPanelConversations';
import { LeftPanelProjects } from '@/features/left-panel/components/LeftPanelProjects';

import { useResponsiveStore } from '@/stores';

export const LeftPanelContent = () => {
  const { isDesktop } = useResponsiveStore();
  const { authenticated } = useAuth();

  return (
    <Box
      $width="100%"
      $css={`
        overflow-y: auto;
        overflow-x: hidden;
        position: relative;
        height: calc(100dvh - ${isDesktop ? '52px' : '104px'});
      `}
    >
      {authenticated && (
        <>
          {' '}
          <LeftPanelProjects /> <LeftPanelConversations />
        </>
      )}
    </Box>
  );
};
