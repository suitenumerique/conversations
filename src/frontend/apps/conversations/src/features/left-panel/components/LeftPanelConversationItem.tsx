import { css } from 'styled-components';

import { Box, StyledLink } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ChatConversation } from '@/features/chat/types';
import { ConversationItemActions } from '@/features/left-panel/components/ConversationItemActions';
import { SimpleConversationItem } from '@/features/left-panel/components/SimpleConversationItem';
import { useResponsiveStore } from '@/stores';

type LeftPanelConversationItemProps = {
  conversation: ChatConversation;
};

export const LeftPanelConversationItem = ({
  conversation,
}: LeftPanelConversationItemProps) => {
  const { spacingsTokens } = useCunninghamTheme();
  const { isDesktop } = useResponsiveStore();

  return (
    <Box
      $direction="row"
      $align="center"
      $justify="space-between"
      $css={css`
        padding: ${spacingsTokens['2xs']};
        border-radius: 4px;
        .pinned-actions {
          opacity: ${isDesktop ? 0 : 1};
        }
        &:hover {
          cursor: pointer;

          background-color: var(--c--theme--colors--greyscale-100);
          .pinned-actions {
            opacity: 1;
          }
        }
      `}
      key={conversation.id}
      className="--docs--left-panel-favorite-item"
    >
      <StyledLink href={`/chat/${conversation.id}/`} $css="overflow: auto;">
        <SimpleConversationItem showAccesses conversation={conversation} />
      </StyledLink>
      <div className="pinned-actions">
        <ConversationItemActions conversation={conversation} />
      </div>
    </Box>
  );
};
