import { Button as _Button, useModal } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, DropdownMenu, DropdownMenuOption, Icon } from '@/components';
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
        <Box
          role="button"
          tabIndex={0}
          aria-label={t('Conversation actions')}
          aria-haspopup="menu"
          aria-expanded="false"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              // Le DropdownMenu gère l'ouverture
            }
          }}
          $css={css`
            display: block;
            width: 24px;
            height: 24px;
            padding: 4px;
            border-radius: 4px;
            cursor: pointer;
            &:hover {
              background-color: #e1e3e7 !important;
            }
            &:focus {
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
        </Box>
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
