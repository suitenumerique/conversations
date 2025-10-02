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
        position: relative;
        height: calc(100dvh - ${isDesktop ? '52px' : '104px'});
      `}
    >
      {!isDesktop && (
        <Box $padding={{ horizontal: 'sm', top: 'sm' }}>
          <Feedback />
        </Box>
      )}
      <Box
        $css={`
          z-index: 100;
          position: sticky;
          top: 0px;
        `}
      >
        <LeftPanelSearch onSearchChange={setHasSearch} />
      </Box>
      {!hasSearch && <LeftPanelConversations />}
    </Box>
  );
};
