import { useTranslation } from 'react-i18next';

import { Box, InfiniteScroll, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useInfiniteConversations } from '@/features/chat/api/useConversations';
import { LeftPanelConversationItem } from '@/features/left-panel/components/LeftPanelConversationItem';

export const LeftPanelConversations = () => {
  const { t } = useTranslation();

  const { spacingsTokens } = useCunninghamTheme();

  const conversations = useInfiniteConversations({
    page: 1,
    ordering: '-updated_at',
  });

  const favoriteConversations =
    conversations.data?.pages.flatMap((page) => page.results) || [];

  if (favoriteConversations.length === 0) {
    return null;
  }

  return (
    <Box className="--conversations--left-panel-favorites">
      <Box
        $justify="center"
        $padding={{ horizontal: 'sm', top: 'sm' }}
        $gap={spacingsTokens['2xs']}
        $height="100%"
        data-testid="left-panel-favorites"
      >
        <Text
          $size="sm"
          $variation="700"
          $padding={{ horizontal: '3xs' }}
          $weight="700"
        >
          {t('Recent conversations')}
        </Text>
        <InfiniteScroll
          hasMore={conversations.hasNextPage}
          isLoading={conversations.isFetchingNextPage}
          next={() => void conversations.fetchNextPage()}
        >
          {favoriteConversations.map((conversation) => (
            <LeftPanelConversationItem
              key={conversation.id}
              conversation={conversation}
            />
          ))}
        </InfiniteScroll>
      </Box>
    </Box>
  );
};
