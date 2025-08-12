import { useState } from 'react';

import { Box } from '@/components';
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
      <LeftPanelSearch onSearchChange={setHasSearch} />
      {!hasSearch && <LeftPanelConversations />}
    </Box>
  );
};
