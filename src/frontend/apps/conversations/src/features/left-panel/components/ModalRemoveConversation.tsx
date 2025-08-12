import { Button, Modal, ModalSize } from '@openfun/cunningham-react';
import { t } from 'i18next';
import { usePathname } from 'next/navigation';
import { useRouter } from 'next/router';

import { Box, Text, TextErrors, useToast } from '@/components';
import { useRemoveConversation } from '@/features/chat/api/useRemoveConversation';
import { ChatConversation } from '@/features/chat/types';

interface ModalRemoveConversationProps {
  onClose: () => void;
  conversation: ChatConversation;
}

export const ModalRemoveConversation = ({
  onClose,
  conversation,
}: ModalRemoveConversationProps) => {
  const { showToast } = useToast();
  const { push } = useRouter();
  const pathname = usePathname();

  const {
    mutate: removeDoc,
    isError,
    error,
  } = useRemoveConversation({
    onSuccess: () => {
      showToast(
        'success',
        t('The conversation has been deleted.'),
        undefined,
        4000,
      );
      if (pathname === '/') {
        onClose();
      } else {
        void push('/');
      }
    },
  });

  return (
    <Modal
      isOpen
      closeOnClickOutside
      onClose={() => onClose()}
      rightActions={
        <>
          <Button
            aria-label={t('Close the modal')}
            color="secondary"
            fullWidth
            onClick={() => onClose()}
          >
            {t('Cancel')}
          </Button>
          <Button
            aria-label={t('Confirm deletion')}
            color="danger"
            fullWidth
            onClick={() =>
              removeDoc({
                conversationId: conversation.id,
              })
            }
          >
            {t('Delete')}
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
          {t('Delete a conversation')}
        </Text>
      }
    >
      <Box
        aria-label={t('Content modal to delete conversation')}
        className="--docs--modal-remove-doc"
      >
        {!isError && (
          <Text $size="sm" $variation="600">
            {t('Are you sure you want to delete this conversation ?')}
          </Text>
        )}

        {isError && <TextErrors causes={error.cause} />}
      </Box>
    </Modal>
  );
};
