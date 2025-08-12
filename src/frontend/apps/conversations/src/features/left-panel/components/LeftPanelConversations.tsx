import { useRouter } from 'next/router';
import { useTranslation } from 'react-i18next';

import { Box, InfiniteScroll, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useInfiniteConversations } from '@/features/chat/api/useConversations';
import { LeftPanelConversationItem } from '@/features/left-panel/components/LeftPanelConversationItem';

export const LeftPanelConversations = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { id } = router.query;

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
        $padding={{ horizontal: 'sm', top: 'sm' }}
        $gap={spacingsTokens['2xs']}
        $height="50vh"
        data-testid="left-panel-favorites"
      >
        <Text
          $size="sm"
          $variation="700"
          $padding={{ horizontal: 'xs' }}
          $weight="700"
        >
          {t('History')}
        </Text>
        <InfiniteScroll
          hasMore={conversations.hasNextPage}
          isLoading={conversations.isFetchingNextPage}
          next={() => void conversations.fetchNextPage()}
        >
          {favoriteConversations.map((conversation) => (
            <LeftPanelConversationItem
              key={conversation.id}
              isCurrentConversation={conversation.id === id}
              conversation={conversation}
            />
          ))}
        </InfiniteScroll>
      </Box>
    </Box>
  );
};
