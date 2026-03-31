import { useCallback, useRef, useState } from 'react';

import { Box } from '@/components';
import { useAuth } from '@/features/auth/hooks';
import { LeftPanelConversations } from '@/features/left-panel/components/left-panel/LeftPanelConversations';
import { LeftPanelProjects } from '@/features/left-panel/components/left-panel/LeftPanelProjects';
import { useResponsiveStore } from '@/stores';

export const LeftPanelContent = () => {
  const { isDesktop } = useResponsiveStore();
  const { authenticated } = useAuth();
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [hasScrolled, setHasScrolled] = useState(false);

  const handleScroll = useCallback(() => {
    if (!contentRef.current) {
      return;
    }
    setHasScrolled(contentRef.current.scrollTop > 0);
  }, []);

  return (
    <Box
      ref={contentRef}
      $width="100%"
      onScroll={handleScroll}
      $css={`
        overflow-y: auto;
        overflow-x: hidden;
        position: relative;
        height: calc(100dvh - ${isDesktop ? '52px' : '104px'});
      `}
      style={{
        borderTop: hasScrolled
          ? '1px solid var(--c--contextuals--border--surface--primary)'
          : 'none',
      }}
    >
      {authenticated && (
        <>
          <LeftPanelProjects /> <LeftPanelConversations />
        </>
      )}
    </Box>
  );
};
