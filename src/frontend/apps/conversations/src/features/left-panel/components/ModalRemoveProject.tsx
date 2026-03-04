import { Button, Modal, ModalSize } from '@openfun/cunningham-react';
import { t } from 'i18next';

import { usePathname } from 'next/navigation';
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
  const { push } = useRouter();
  const pathname = usePathname();

  const { mutate: removeProject } = useRemoveProject({
    onSuccess: () => {
      showToast(
        'success',
        t('The project has been deleted.'),
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
      aria-label={t('Content modal to delete project')}
      rightActions={
        <>
                  <Button
            aria-label={t('Confirm deletion')}
            color="error"
            variant="bordered"
            fullWidth
            onClick={() =>
              removeProject({
                projectId: project.id,
              })
            }
          >
            {t('Delete anyway')}
          </Button>
          <Button
            aria-label={t('Close the modal')}
            color="brand"

            fullWidth
            onClick={() => onClose()}
          >
            {t('Cancel')}
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
          {t('Are you sure you want to delete the “{{title}}” project? All associated conversations and embedded' +
              ' documents will be permanently lost.', { title: project.title })}
        </Text>
      </Box>
    </Modal>
  );
};
