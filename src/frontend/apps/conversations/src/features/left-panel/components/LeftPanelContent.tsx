import { useState } from 'react';

import { Box } from '@/components';
import { Feedback } from '@/features/feedback/Feedback';
import { LeftPanelConversations } from '@/features/left-panel/components/LeftPanelConversations';
import { LeftPanelSearch } from '@/features/left-panel/components/LeftPanelSearch';
import { useResponsiveStore } from '@/stores';

export const LeftPanelContent = () => {
  const { isDesktop } = useResponsiveStore();
  const [hasSearch, setHasSearch] = useState(false);

  return (
    <Box
      $width="100%"
      $css={`
        overflow-y: auto;
        overflow-x: hidden;
        height: calc(100dvh - ${isDesktop ? '52px' : '104px'});
      `}
    >
      {!isDesktop && (
        <Box $padding={{ horizontal: 'sm', top: 'sm' }}>
          <Feedback />
        </Box>
      )}
      <Box
        $position="sticky"
        $zIndex="100"
        $css={`
          top: 0;
          background: linear-gradient(
            to bottom,
            rgba(255, 255, 255, 1) 0%,
            rgba(255, 255, 255, 1) 70%,
            rgba(255, 255, 255, 0) 100%
          );
        `}
      >
        <LeftPanelSearch onSearchChange={setHasSearch} />
      </Box>
      {!hasSearch && <LeftPanelConversations />}
    </Box>
  );
};
