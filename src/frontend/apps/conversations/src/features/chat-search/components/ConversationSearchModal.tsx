import { Modal, ModalSize } from '@openfun/cunningham-react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InView } from 'react-intersection-observer';
import { useDebouncedCallback } from 'use-debounce';

import { Box, Text } from '@/components';
import {
  QuickSearch,
  QuickSearchData,
  QuickSearchGroup,
} from '@/components/quick-search';
import { useInfiniteConversations } from '@/features/chat/api/useConversations';
import { ChatConversation } from '@/features/chat/types';
import { useResponsiveStore } from '@/stores';

import EmptySearchIcon from '../assets/illustration-docs-empty.png';

import { ConversationSearchItem } from './ConversationSearchItem';

type ConversationSearchModalProps = {
  onClose: () => void;
  isOpen: boolean;
};

export const ConversationSearchModal = ({
  ...modalProps
}: ConversationSearchModalProps) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [search, setSearch] = useState('');
  const { isDesktop } = useResponsiveStore();
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
  const handleInputSearch = useDebouncedCallback(setSearch, 300);

  const handleSelect = (conversation: ChatConversation) => {
    router.push(`/chat/${conversation.id}`);
    modalProps.onClose?.();
  };

  const conversationsData: QuickSearchData<ChatConversation> = useMemo(() => {
    const conversations = data?.pages.flatMap((page) => page.results) || [];

    return {
      groupName: conversations.length > 0 ? t('Select a chat') : '',
      elements: search ? conversations : [],
      emptyString: t('No conversation found'),
      endActions: hasNextPage
        ? [{ content: <InView onChange={() => void fetchNextPage()} /> }]
        : [],
    };
  }, [data, hasNextPage, fetchNextPage, t, search]);

  return (
    <Modal
      {...modalProps}
      closeOnClickOutside
      size={isDesktop ? ModalSize.LARGE : ModalSize.FULL}
    >
      <Box
        aria-label={t('Search modal')}
        $direction="column"
        $justify="space-between"
        className="--docs--doc-search-modal"
      >
        <Text
          $padding={{ all: 'base', bottom: 'none', top: 'xs' }}
          $size="sm"
          $weight="600"
        >
          {t('Search for a chat')}
        </Text>
        <QuickSearch
          placeholder={t('Type a keyword related to a previous chat')}
          loading={loading}
          onFilter={handleInputSearch}
        >
          <Box $height={isDesktop ? '500px' : 'calc(100vh - 68px - 1rem)'}>
            {search.length === 0 && (
              <Box
                $direction="column"
                $height="100%"
                $align="center"
                $justify="center"
              >
                <Image
                  className="c__image-system-filter"
                  width={320}
                  src={EmptySearchIcon}
                  alt={t('No active search')}
                />
              </Box>
            )}
            {search && (
              <QuickSearchGroup
                onSelect={handleSelect}
                group={conversationsData}
                renderElement={(conversation) => (
                  <ConversationSearchItem conversation={conversation} />
                )}
              />
            )}
          </Box>
        </QuickSearch>
      </Box>
    </Modal>
  );
};
