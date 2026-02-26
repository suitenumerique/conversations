import { Modal, ModalSize } from '@openfun/cunningham-react';
import { useRouter } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InView } from 'react-intersection-observer';
import { useDebouncedCallback } from 'use-debounce';

import { Box } from '@/components';
import {
  QuickSearch,
  QuickSearchData,
  QuickSearchGroup,
  QuickSearchResultItem,
} from '@/components/quick-search';
import { useInfiniteConversations } from '@/features/chat/api/useConversations';
import { ChatConversation } from '@/features/chat/types';

type LeftPanelSearchModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

const SEARCH_DEBOUNCE_MS = 400;

export const LeftPanelSearchModal = ({
  isOpen,
  onClose,
}: LeftPanelSearchModalProps) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [inputValue, setInputValue] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const debouncedSetSearchQuery = useDebouncedCallback(
    (value: string) => setSearchQuery(value),
    SEARCH_DEBOUNCE_MS,
  );

  const handleInputChange = useCallback(
    (value: string) => {
      setInputValue(value);
      debouncedSetSearchQuery(value);
    },
    [debouncedSetSearchQuery],
  );

  const { data, fetchNextPage, hasNextPage } = useInfiniteConversations({
    page: 1,
    title: searchQuery,
  });

  const handleSelect = useCallback(
    (conversation: ChatConversation) => {
      router.push(`/chat/${conversation.id}`);
      onClose();
    },
    [router, onClose],
  );

  const renderElement = useCallback(
    (conversation: ChatConversation) => (
      <QuickSearchResultItem conversation={conversation} />
    ),
    [],
  );

  const endActionsContent = useMemo(
    () =>
      hasNextPage
        ? [{ content: <InView onChange={() => void fetchNextPage()} /> }]
        : [],
    [hasNextPage, fetchNextPage],
  );

  const conversationsData: QuickSearchData<ChatConversation> = useMemo(() => {
    const conversations = data?.pages.flatMap((page) => page.results) || [];

    return {
      groupName: conversations.length > 0 ? t('Select a chat') : '',
      elements: searchQuery ? conversations : [],
      emptyString: t('No conversation found'),
      endActions: endActionsContent,
    };
  }, [data, searchQuery, t, endActionsContent]);

  return (
    <Modal
      isOpen={isOpen}
      closeOnClickOutside
      onClose={onClose}
      size={ModalSize.MEDIUM}
      title={t('Search for a chat')}
    >
      <Box className="quick-search-container" $padding={{ top: 'xs' }}>
        <QuickSearch
          placeholder={t('Type a keyword')}
          onFilter={handleInputChange}
          inputValue={inputValue}
          hasResults={conversationsData.elements.length > 0}
        >
          <Box>
            {searchQuery && (
              <QuickSearchGroup
                onSelect={handleSelect}
                group={conversationsData}
                renderElement={renderElement}
              />
            )}
          </Box>
        </QuickSearch>
      </Box>
    </Modal>
  );
};
