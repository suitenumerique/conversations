import { memo, useCallback, useMemo } from 'react';
import { css } from 'styled-components';

import { Box, StyledLink } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { ChatConversation } from '@/features/chat/types';
import { ConversationItemActions } from '@/features/left-panel/components/ConversationItemActions';
import { SimpleConversationItem } from '@/features/left-panel/components/SimpleConversationItem';
import { useResponsiveStore } from '@/stores';

type LeftPanelConversationItemProps = {
  conversation: ChatConversation;
  isCurrentConversation: boolean;
};

const linkStyles = css`
  overflow: auto;
  flex-grow: 1;
  color: var(--c--theme--colors--greyscale-900);
`;

const baseBoxStyles = css`
  border-radius: 4px;
  width: 100%;
  margin-bottom: 1px;

  transition: background-color 0.2s cubic-bezier(1, 0, 0, 1);

  &:hover,
  &:focus,
  &:focus-within {
    background-color: #ebedf1;
    .pinned-actions {
      opacity: 1;
    }
  }
  .pinned-actions:focus-within {
    opacity: 1;
  }
`;

const getBoxStyles = (
  isCurrentConversation: boolean,
  isDesktop: boolean,
) => css`
  ${baseBoxStyles}
  background-color: ${isCurrentConversation ? '#ebedf1' : 'transparent'};
  font-weight: ${isCurrentConversation ? '700' : '500'};

  .pinned-actions {
    padding: 2px 0;
    opacity: ${isDesktop ? 0 : 1};
    background-color: transparent;
    transition: all 0.3s cubic-bezier(1, 0, 0, 1);
  }
`;

const containerPadding = { horizontal: 'xs', vertical: '4px' };

export const LeftPanelConversationItem = memo(
  function LeftPanelConversationItem({
    conversation,
    isCurrentConversation,
  }: LeftPanelConversationItemProps) {
    const isDesktop = useResponsiveStore((state) => state.isDesktop);
    const setPanelOpen = useChatPreferencesStore((state) => state.setPanelOpen);

    const handleLinkClick = useCallback(() => {
      if (!isDesktop) {
        setPanelOpen(false);
      }
    }, [isDesktop, setPanelOpen]);

    const boxStyles = useMemo(
      () => getBoxStyles(isCurrentConversation, isDesktop),
      [isCurrentConversation, isDesktop],
    );

    return (
      <Box
        $direction="row"
        $align="center"
        $padding={containerPadding}
        $justify="space-between"
        $css={boxStyles}
        className="--docs--left-panel-favorite-item"
      >
        <StyledLink
          href={`/chat/${conversation.id}/`}
          $css={linkStyles}
          onClick={handleLinkClick}
        >
          <SimpleConversationItem showAccesses conversation={conversation} />
        </StyledLink>

        <Box className="pinned-actions">
          <ConversationItemActions conversation={conversation} />
        </Box>
      </Box>
    );
  },
);
