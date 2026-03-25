import { Button, Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import { t } from 'i18next';
import { useRouter } from 'next/router';

import { Box, Text, useToast } from '@/components';
import { useRemoveProject } from '@/features/chat/api/useRemoveProject';

interface ModalRemoveProjectProps {
  onClose: () => void;
  project: { id: string; title: string };
}

export const ModalRemoveProject = ({
  onClose,
  project,
}: ModalRemoveProjectProps) => {
  const { showToast } = useToast();
  const { push, pathname } = useRouter();

  const { mutate: removeProject, isPending: isRemoving } = useRemoveProject({
    onSuccess: () => {
      showToast('success', t('The project has been deleted.'), undefined, 4000);
      if (pathname === '/') {
        onClose();
      } else {
        void push('/');
      }
    },
    onError: (error) => {
      const errorMessage =
        error.cause?.[0] ||
        error.message ||
        t('An error occurred while deleting the project');
      showToast('error', errorMessage, undefined, 4000);
    },
  });

  return (
    <Modal
      isOpen
      closeOnClickOutside
      onClose={() => onClose()}
      aria-label={t('Content modal to delete project')}
      rightActions={
        <>
          <Button
            aria-label={t('Close the modal')}
            color="neutral"
            variant="bordered"
            fullWidth
            onClick={() => onClose()}
          >
            {t('Cancel')}
          </Button>
          <Button
            aria-label={t('Confirm deletion')}
            color="error"
            variant="primary"
            fullWidth
            disabled={isRemoving}
            onClick={() =>
              removeProject({
                projectId: project.id,
              })
            }
          >
            {t('Delete')}
          </Button>
        </>
      }
      size={ModalSize.MEDIUM}
      title={
        <Text
          $size="h6"
          as="h6"
          $margin={{ all: '0' }}
          $align="flex-start"
          $variation="1000"
        >
          {t('Delete {{title}}', { title: project.title })}
        </Text>
      }
    >
      <Box
        className="--conversations--modal-remove-project"
        data-testid="delete-project-confirm"
      >
        <Text $size="sm" $variation="600">
          {t(
            'Are you sure you want to delete the "{{title}}" project? All associated conversations and embedded' +
              ' documents will be permanently lost.',
            { title: project.title },
          )}
        </Text>
      </Box>
    </Modal>
  );
};
