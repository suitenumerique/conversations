import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Icon } from '@gouvfr-lasuite/ui-kit';
import { DropdownMenu, DropdownMenuOption } from '@/components';
import { ChatProject } from '@/features/chat/types';
import { useOwnModal } from '@/features/left-panel/hooks/useModalHook';

import { ModalProjectForm } from './ModalProjectForm';
import { ModalRemoveProject } from './ModalRemoveProject';

interface ProjectItemActionsProps {
  project: ChatProject;
}

export const ProjectItemActions = ({ project }: ProjectItemActionsProps) => {
  const { t } = useTranslation();

  const deleteModal = useOwnModal();
  const settingsModal = useOwnModal();

  const options: DropdownMenuOption[] = useMemo(
    () => [
      {
        label: t('Project settings'),
        icon: 'settings',
        callback: settingsModal.open,
        disabled: false,
        testId: `project-item-actions-settings-${project.id}`,
      },
      {
        label: t('Delete project'),
        icon: 'delete',
        callback: deleteModal.open,
        disabled: false,
        testId: `project-item-actions-remove-${project.id}`,
      },
    ],
    [t, project.id, settingsModal.open, deleteModal.open],
  );
  const dropdownLabel = useMemo(
    () =>
      t('Actions list for project {{title}}', {
        title: project.title,
      }),
    [t, project.title],
  );

  return (
    <>
      <DropdownMenu
        options={options}
        label={dropdownLabel}
        buttonCss={css`
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          padding: 4px;
          border-radius: 4px;
          &&:hover {
            background-color: var(
              --c--contextuals--background--semantic--overlay--primary
            );
          }
          &:focus-visible {
            outline: 2px solid
              var(--c--contextuals--content--semantic--brand--tertiary);
            outline-offset: 2px;
          }
        `}
      >
        <Icon
          data-testid={`project-item-actions-button-${project.id}`}
          name="more_horiz"
          color="var(--c--globals--colors--brand-550)"
        />
      </DropdownMenu>

      {deleteModal.isOpen && (
        <ModalRemoveProject onClose={deleteModal.close} project={project} />
      )}
      {settingsModal.isOpen && (
        <ModalProjectForm onClose={settingsModal.close} project={project} />
      )}
    </>
  );
};
