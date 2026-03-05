import { memo } from 'react';

import { ChatConversation } from '@/features/chat/types';
import { ConversationItemActions } from '@/features/left-panel/components/ConversationItemActions';
import { ConversationRow } from '@/features/left-panel/components/ConversationRow';
import { SimpleConversationItem } from '@/features/left-panel/components/SimpleConversationItem';

type LeftPanelConversationItemProps = {
  conversation: ChatConversation;
  isCurrentConversation: boolean;
  /** Displays the time since the last message (e.g., in the search modal) */
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
