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

export const LeftPanelConversationItem = ({
  conversation,
  isCurrentConversation,
}: LeftPanelConversationItemProps) => {
  const { isDesktop } = useResponsiveStore();
  const { setPanelOpen } = useChatPreferencesStore();

  const handleLinkClick = () => {
    if (!isDesktop) {
      setPanelOpen(false);
    }
  };

  return (
    <Box
      $direction="row"
      $align="center"
      $padding={{ horizontal: 'xs', vertical: '4px' }}
      $justify="space-between"
      $css={css`
        border-radius: 4px;
        width: 100%;
        margin-bottom: 1px;
        background-color: ${isCurrentConversation ? 'var(--c--contextuals--background--semantic--overlay--primary)' : ''};
        font-weight: ${isCurrentConversation ? '700' : '500'};
        transition: background-color 0.2s cubic-bezier(1, 0, 0, 1);
        .pinned-actions {
          padding: 2px 0;
          opacity: ${isDesktop ? 0 : 1};
          background-color: transparent
          transition: all 0.3s cubic-bezier(1, 0, 0, 1);
        }
        &:hover, &:focus, &:focus-within {
          background-color: var(--c--contextuals--background--semantic--overlay--primary);
          .pinned-actions {
            opacity: 1;
          }
        }
        .pinned-actions:focus-within {
          opacity: 1;
        }
      `}
      className="--docs--left-panel-favorite-item"
    >
      <StyledLink
        href={`/chat/${conversation.id}/`}
        $css="overflow: auto; flex-grow: 1; color: var(--c--theme--colors--greyscale-900);"
        onClick={handleLinkClick}
      >
        <SimpleConversationItem showAccesses conversation={conversation} />
      </StyledLink>

      <Box className="pinned-actions">
        <ConversationItemActions conversation={conversation} />
      </Box>
    </Box>
  );
};
