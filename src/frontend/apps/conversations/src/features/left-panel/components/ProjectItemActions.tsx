import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { DropdownMenu, DropdownMenuOption, Icon } from '@/components';
import { ChatProject } from '@/features/chat/types';
import { useOwnModal } from '@/features/left-panel/hooks/useModalHook';

import { ModalProjectSettings } from './ModalProjectSettings';
import { ModalRemoveProject } from './ModalRemoveProject';

interface ProjectItemActionsProps {
  project: ChatProject;
}

export const ProjectItemActions = ({ project }: ProjectItemActionsProps) => {
  const { t } = useTranslation();

  const deleteModal = useOwnModal();
  const settingsModal = useOwnModal();

  const options: DropdownMenuOption[] = [
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
  ];
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
          &:hover {
            background-color: var(
              --c--contextuals--background--semantic--overlay--primary
            ) !important;
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
          iconName="more_horiz"
          $theme="brand"
          $variation="tertiary"
        />
      </DropdownMenu>

      {deleteModal.isOpen && (
        <ModalRemoveProject onClose={deleteModal.close} project={project} />
      )}
      {settingsModal.isOpen && (
        <ModalProjectSettings onClose={settingsModal.close} project={project} />
      )}
    </>
  );
};
