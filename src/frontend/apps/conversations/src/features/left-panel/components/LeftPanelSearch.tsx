import { useParams, useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InView } from 'react-intersection-observer';
import { useDebouncedCallback } from 'use-debounce';

import { Box } from '@/components';
import {
  QuickSearch,
  QuickSearchData,
  QuickSearchGroup,
} from '@/components/quick-search';
import { useInfiniteConversations } from '@/features/chat/api/useConversations';
import { ChatConversation } from '@/features/chat/types';
import { LeftPanelConversationItem } from '@/features/left-panel/components/LeftPanelConversationItem';
import { useResponsiveStore } from '@/stores';

type LeftPanelSearchProps = {
  onSearchChange?: (hasSearch: boolean) => void;
};

export const LeftPanelSearch = ({ onSearchChange }: LeftPanelSearchProps) => {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams();
  const [search, setSearch] = useState('');
  const { isDesktop: _isDesktop } = useResponsiveStore();

  const currentConversationId = params?.id as string;

  const {
    data,
    isFetching,
    isRefetching,
    isLoading,
    fetchNextPage,
    hasNextPage,
  } = useInfiniteConversations({
    page: 1,
    title: search,
  });

  const loading = isFetching || isRefetching || isLoading;
  const handleInputSearch = useDebouncedCallback((value: string) => {
    setSearch(value);
    onSearchChange?.(value.length > 0);
  }, 300);

  const handleSelect = (conversation: ChatConversation) => {
    router.push(`/chat/${conversation.id}`);
  };

  const handleClear = () => {
    setSearch('');
    onSearchChange?.(false);
  };

  const conversationsData: QuickSearchData<ChatConversation> = useMemo(() => {
    const conversations = data?.pages.flatMap((page) => page.results) || [];

    return {
      groupName: conversations.length > 0 ? t('Search results') : '',
      elements: search ? conversations : [],
      emptyString: t('No conversation found'),
      endActions: hasNextPage
        ? [{ content: <InView onChange={() => void fetchNextPage()} /> }]
        : [],
    };
  }, [data, hasNextPage, fetchNextPage, t, search]);

  return (
    <QuickSearch
      placeholder={t('Search for a chat')}
      loading={loading}
      onFilter={handleInputSearch}
      onClear={handleClear}
      inputValue={search}
    >
      <Box>
        {search && (
          <QuickSearchGroup
            onSelect={handleSelect}
            group={conversationsData}
            renderElement={(conversation) => (
              <LeftPanelConversationItem
                conversation={conversation}
                isCurrentConversation={
                  conversation.id === currentConversationId
                }
              />
            )}
          />
        )}
      </Box>
    </QuickSearch>
  );
};
