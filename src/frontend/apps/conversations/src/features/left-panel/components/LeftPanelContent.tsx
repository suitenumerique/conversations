import { Box } from '@/components';
import { LeftPanelConversations } from '@/features/left-panel/components/LeftPanelConversations';

export const LeftPanelContent = () => {
  return (
    <Box $flex={1} $width="100%" $css="overflow-y: auto; overflow-x: hidden;">
      <LeftPanelConversations />
    </Box>
  );
};
