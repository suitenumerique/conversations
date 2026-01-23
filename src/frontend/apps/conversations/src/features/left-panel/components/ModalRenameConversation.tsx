import { Button, Input, Modal, ModalSize } from '@openfun/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text, useToast } from '@/components';
import { useRenameConversation } from '@/features/chat/api/useRenameConversation';
import { ChatConversation } from '@/features/chat/types';

interface ModalRenameConversationProps {
  onClose: () => void;
  conversation: ChatConversation;
}

export const ModalRenameConversation = ({
  onClose,
  conversation,
}: ModalRenameConversationProps) => {
  const { showToast } = useToast();
  const { t } = useTranslation();
  const { mutate: renameConversation } = useRenameConversation({
    onSuccess: () => {
      showToast(
        'success',
        t('The conversation has been renamed.'),
        undefined,
        4000,
      );
      onClose();
    },
    onError: (error) => {
      const errorMessage =
        error.cause?.[0] ||
        error.message ||
        t('An error occurred while renaming the conversation');
      showToast('error', errorMessage, undefined, 4000);
    },
  });

  const [newName, setNewName] = useState(conversation.title ?? '');
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedNewName = newName.trim();
    if (trimmedNewName) {
      renameConversation({
        conversationId: conversation.id,
        title: trimmedNewName,
      });
    }
  };
  return (
    <Modal
      isOpen
      closeOnClickOutside
      onClose={() => onClose()}
      aria-label={t('Content modal to rename a conversation')}
      rightActions={
        <>
          <Button
            aria-label={t('Close the modal')}
            color="brand"
            variant="bordered"
            onClick={() => onClose()}
          >
            {t('Cancel')}
          </Button>
          <Button
            aria-label={t('Rename chat')}
            color="brand"
            variant="primary"
            type="submit"
            form="rename-chat-form"
          >
            {t('Rename')}
          </Button>
        </>
      }
      size={ModalSize.SMALL}
      title={
        <Text
          $size="h6"
          as="h6"
          $margin={{ all: '0' }}
          $align="flex-start"
          $variation="1000"
        >
          {t('Rename chat')}
        </Text>
      }
    >
      <Box className="--conversations--modal-rename-chat">
        <form
          onSubmit={handleSubmit}
          id="rename-chat-form"
          data-testid="rename-chat-form"
          className="mt-s"
        >
          <Input
            type="text"
            label={t('New name')}
            maxLength={100}
            value={newName}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setNewName(e.target.value);
            }}
          />
        </form>
      </Box>
    </Modal>
  );
};
