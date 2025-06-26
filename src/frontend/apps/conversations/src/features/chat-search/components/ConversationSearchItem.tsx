import { Box, Icon } from '@/components';
import { QuickSearchItemContent } from '@/components/quick-search/';
import { ChatConversation } from '@/features/chat/types';
import { SimpleConversationItem } from '@/features/left-panel/components/SimpleConversationItem';
import { useResponsiveStore } from '@/stores';

type ConversationSearchItemProps = {
  conversation: ChatConversation;
};

export const ConversationSearchItem = ({
  conversation,
}: ConversationSearchItemProps) => {
  const { isDesktop } = useResponsiveStore();
  return (
    <Box
      data-testid={`doc-search-item-${conversation.id}`}
      $width="100%"
      className="--docs--doc-search-item"
    >
      <QuickSearchItemContent
        left={
          <Box $direction="row" $align="center" $gap="10px" $width="100%">
            <Box $flex={isDesktop ? 9 : 1}>
              <SimpleConversationItem
                conversation={conversation}
                showAccesses
              />
            </Box>
          </Box>
        }
        right={
          <Icon iconName="keyboard_return" $theme="primary" $variation="800" />
        }
      />
    </Box>
  );
};
