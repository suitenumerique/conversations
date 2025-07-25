import { Button, useModal } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { DropdownMenu, DropdownMenuOption, Icon } from '@/components';
import { ChatConversation } from '@/features/chat/types';

import { ModalRemoveConversation } from './ModalRemoveConversation';

interface ConversationItemActionsProps {
  conversation: ChatConversation;
}

export const ConversationItemActions = ({
  conversation,
}: ConversationItemActionsProps) => {
  const { t } = useTranslation();

  const deleteModal = useModal();

  const options: DropdownMenuOption[] = [
    {
      label: t('Delete chat'),
      icon: 'delete',
      callback: () => deleteModal.open(),
      disabled: false,
      testId: `conversation-item-actions-remove-${conversation.id}`,
    },
  ];

  return (
    <>
      <DropdownMenu options={options}>
        <Button
          size="medium"
          aria-label={t('Open the modal delete chat')}
          color="tertiary-text"
          icon={
            <Icon
              data-testid={`conversation-item-actions-button-${conversation.id}`}
              iconName="more_horiz"
              $theme="primary"
              $variation="600"
            />
          }
        ></Button>
      </DropdownMenu>

      {deleteModal.isOpen && (
        <ModalRemoveConversation
          onClose={deleteModal.onClose}
          conversation={conversation}
        />
      )}
    </>
  );
};
