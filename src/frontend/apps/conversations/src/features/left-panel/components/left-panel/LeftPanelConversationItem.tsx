import { memo } from 'react';

import { ChatConversation } from '@/features/chat/types';
import { ConversationItemActions } from '@/features/left-panel/components/ConversationItemActions';
import { ConversationRow } from '@/features/left-panel/components/ConversationRow';
import { SimpleConversationItem } from '@/features/left-panel/components/SimpleConversationItem';

type LeftPanelConversationItemProps = {
  conversation: ChatConversation;
  isCurrentConversation: boolean;
  /** Affiche le temps depuis le dernier message (ex. dans la modale de recherche) */
  showUpdatedAt?: boolean;
};

export const LeftPanelConversationItem = memo(
  function LeftPanelConversationItem({
    conversation,
    isCurrentConversation,
    showUpdatedAt = false,
  }: LeftPanelConversationItemProps) {
    return (
      <ConversationRow
        conversationId={conversation.id}
        isActive={isCurrentConversation}
        actions={<ConversationItemActions conversation={conversation} />}
      >
        <SimpleConversationItem
          showAccesses
          showUpdatedAt={showUpdatedAt}
          conversation={conversation}
        />
      </ConversationRow>
    );
  },
);
