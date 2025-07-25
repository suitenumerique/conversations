import { css } from 'styled-components';

import { Box, StyledLink } from '@/components';
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
  // const { togglePanel } = useLeftPanelStore();

  return (
    <Box
      $direction="row"
      $align="center"
      $padding={{ horizontal: 'xs' }}
      $justify="space-between"
      $css={css`
        border-radius: 4px;
        width: 100%;
        background-color: ${isCurrentConversation ? '#eaecee' : ''};
        font-weight: ${isCurrentConversation ? '700' : '500'};
        .pinned-actions {
          opacity: ${isDesktop ? 0 : 1};
        }
        &:hover {
          background-color: var(--c--theme--colors--greyscale-100);
          .pinned-actions {
            opacity: 1;
          }
        }
      `}
      className="--docs--left-panel-favorite-item"
    >
      <StyledLink
        href={`/chat/${conversation.id}/`}
        $css="overflow: auto; flex-grow: 1;"
      >
        {/*To do : close panel onClick*/}
        <SimpleConversationItem showAccesses conversation={conversation} />
      </StyledLink>

      <div className="pinned-actions">
        <ConversationItemActions conversation={conversation} />
      </div>
    </Box>
  );
};
