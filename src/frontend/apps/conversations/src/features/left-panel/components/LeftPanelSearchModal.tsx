import { Modal, ModalSize } from '@openfun/cunningham-react';
import { keepPreviousData } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  onClose: () => void;
};

const SEARCH_DEBOUNCE_MS = 400;
const MIN_SEARCH_LENGTH = 3;
const LOADER_DELAY_MS = 300;

export const LeftPanelSearchModal = ({
  onClose,
}: LeftPanelSearchModalProps) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [inputValue, setInputValue] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const debouncedSetSearchQuery = useDebouncedCallback((value: string) => {
    const trimmed = value.trim();
    setSearchQuery(trimmed.length >= MIN_SEARCH_LENGTH ? trimmed : '');
  }, SEARCH_DEBOUNCE_MS);

  const handleClose = useCallback(() => {
    debouncedSetSearchQuery.cancel();
    onClose();
  }, [onClose, debouncedSetSearchQuery]);

  const handleInputChange = useCallback(
    (value: string) => {
      setInputValue(value);
      debouncedSetSearchQuery(value);
    },
    [debouncedSetSearchQuery],
  );

  // Only fetch when query is non-empty; keep previous results visible during refetch
  const { data, fetchNextPage, hasNextPage, isFetching } =
    useInfiniteConversations(
      {
        page: 1,
        title: searchQuery,
      },
      {
        enabled: Boolean(searchQuery),
        placeholderData: keepPreviousData,
      },
    );

  // Defer loader display to avoid icon flicker on fast responses
  const [showLoader, setShowLoader] = useState(false);
  const loaderTimeout = useRef<ReturnType<typeof setTimeout>>(null);
  useEffect(() => {
    if (isFetching) {
      loaderTimeout.current = setTimeout(
        () => setShowLoader(true),
        LOADER_DELAY_MS,
      );
    } else {
      if (loaderTimeout.current) clearTimeout(loaderTimeout.current);
      setShowLoader(false);
    }
    return () => {
      if (loaderTimeout.current) clearTimeout(loaderTimeout.current);
    };
  }, [isFetching]);

  const handleSelect = useCallback(
    (conversation: ChatConversation) => {
      router.push(`/chat/${conversation.id}`);
      handleClose();
    },
    [router, handleClose],
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
      isOpen
      closeOnClickOutside
      onClose={handleClose}
      size={ModalSize.MEDIUM}
      title={t('Search for a chat')}
    >
      <Box className="quick-search-container" $padding={{ top: 'xs' }}>
        <QuickSearch
          placeholder={t('Type a keyword')}
          onFilter={handleInputChange}
          inputValue={inputValue}
          loading={showLoader}
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
