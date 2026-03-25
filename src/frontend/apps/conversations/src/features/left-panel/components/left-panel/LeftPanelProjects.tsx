import { useRouter } from 'next/router';
import { useTranslation } from 'react-i18next';

import { Box, InfiniteScroll, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useInfiniteProjects } from '@/features/chat/api/useProjects';
import { LeftPanelProjectItem } from '@/features/left-panel/components/left-panel/LeftPanelProjectItem';

export const LeftPanelProjects = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { id } = router.query;

  const { spacingsTokens } = useCunninghamTheme();

  const projects = useInfiniteProjects({
    page: 1,
  });

  const mainProjects =
    projects.data?.pages.flatMap((page) => page.results) || [];

  if (mainProjects.length === 0) {
    return null;
  }

  return (
    <Box
      $padding={{ horizontal: 'sm' }}
      $margin={{ vertical: 'base' }}
      $gap={spacingsTokens['2xs']}
      data-testid="left-panel-projects"
    >
      <Text
        $size="xs"
        $theme="neutral"
        $textTransform="uppercase"
        $variation="tertiary"
        $padding={{ horizontal: 'xs', bottom: '6px' }}
        $weight="500"
      >
        {t('Projects')}
      </Text>

      <InfiniteScroll
        hasMore={projects.hasNextPage}
        isLoading={projects.isFetchingNextPage}
        next={() => void projects.fetchNextPage()}
      >
        {mainProjects.map((prj) => (
          <LeftPanelProjectItem
            key={prj.id}
            currentConversationId={typeof id === 'string' ? id : undefined}
            project={prj}
          />
        ))}
      </InfiniteScroll>
    </Box>
  );
};
