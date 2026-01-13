import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { DropdownMenu, DropdownMenuOption, Icon } from '@/components';
import { ChatConversation } from '@/features/chat/types';
import { useOwnModal } from '@/features/left-panel/hooks/useModalHook';

import { ModalRemoveConversation } from './ModalRemoveConversation';
import { ModalRenameConversation } from './ModalRenameConversation';

interface ConversationItemActionsProps {
  conversation: ChatConversation;
}

const dropdownStyles = css`
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
`;

const iconStyles = css`
  font-size: 1rem;
  color: var(--c--theme--colors--primary-text-text);
  pointer-events: none;
`;

export const ConversationItemActions = ({
  conversation,
}: ConversationItemActionsProps) => {
  const { t } = useTranslation();

  const deleteModal = useOwnModal();
  const renameModal = useOwnModal();

  const options: DropdownMenuOption[] = [
    {
      label: t('Rename chat'),
      icon: 'edit',
      callback: renameModal.open,
      disabled: false,
      testId: `conversation-item-actions-rename-${conversation.id}`,
    },
    {
      label: t('Delete chat'),
      icon: 'delete',
      callback: deleteModal.open,
      disabled: false,
      testId: `conversation-item-actions-remove-${conversation.id}`,
    },
  ];
  const dropdownLabel = useMemo(
    () =>
      t('Actions list for conversation {{title}}', {
        title: conversation.title || t('Untitled conversation'),
      }),
    [t, conversation.title],
  );

  return (
    <>
      <DropdownMenu
        options={options}
        label={dropdownLabel}
        buttonCss={dropdownStyles}
      >
        <Icon
          data-testid={`conversation-item-actions-button-${conversation.id}`}
          iconName="more_horiz"
          $theme="primary"
          $variation="600"
          $css={iconStyles}
        />
      </DropdownMenu>

      {deleteModal.isOpen && (
        <ModalRemoveConversation
          onClose={deleteModal.close}
          conversation={conversation}
        />
      )}
      {renameModal.isOpen && (
        <ModalRenameConversation
          onClose={renameModal.close}
          conversation={conversation}
        />
      )}
    </>
  );
};
