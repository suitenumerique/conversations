import { useModal } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { DropdownMenu, DropdownMenuOption, Icon } from '@/components';
import { ChatConversation } from '@/features/chat/types';

import { ModalRemoveConversation } from './ModalRemoveConversation';
import { ModalRenameConversation } from './ModalRenameConversation';

interface ConversationItemActionsProps {
  conversation: ChatConversation;
}

export const ConversationItemActions = ({
  conversation,
}: ConversationItemActionsProps) => {
  const { t } = useTranslation();

  const deleteModal = useModal();
  const renameModal = useModal();

  const options: DropdownMenuOption[] = [
    {
      label: t('Rename chat'),
      icon: 'edit',
      callback: () => renameModal.open(),
      disabled: false,
      testId: `conversation-item-actions-rename-${conversation.id}`,
    },
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
      <DropdownMenu
        options={options}
        label={t('Actions list for conversation {{title}}', {
          title: conversation.title || t('Untitled conversation'),
        })}
        buttonCss={css`
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          padding: 4px;
          border-radius: 4px;
          &:hover {
            background-color: #e1e3e7 !important;
          }
          &:focus-visible {
            outline: 2px solid #3e5de7;
            outline-offset: 2px;
          }
        `}
      >
        <Icon
          data-testid={`conversation-item-actions-button-${conversation.id}`}
          iconName="more_horiz"
          $theme="primary"
          $variation="600"
          $css={css`
            font-size: 1rem;
            color: var(--c--theme--colors--primary-text-text);
            pointer-events: none;
          `}
        />
      </DropdownMenu>

      {deleteModal.isOpen && (
        <ModalRemoveConversation
          onClose={deleteModal.onClose}
          conversation={conversation}
        />
      )}
      {renameModal.isOpen && (
        <ModalRenameConversation
          onClose={renameModal.onClose}
          conversation={conversation}
        />
      )}
    </>
  );
};
