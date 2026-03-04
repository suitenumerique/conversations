import { Button, Input, Modal, ModalSize } from '@openfun/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Text, useToast } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useUpdateProject } from '@/features/chat/api/useUpdateProject';
import { ChatProject } from '@/features/chat/types';
import { useOwnModal } from '@/features/left-panel/hooks/useModalHook';

import { PROJECT_COLORS, PROJECT_ICONS } from './project-constants';
import { ModalIconColorPicker } from './ModalIconColorPicker';

const textareaCss = css`
  width: 100%;
  min-height: 120px;
  padding: var(--c--globals--spacings--xs);
  border: 1px solid var(--c--contextuals--border--semantic--neutral--default);
  border-radius: 4px;
  font-family: var(--c--globals--font--families--base);
  font-size: 0.875rem;
  resize: vertical;

  &:focus {
    outline: none;
    border-color: var(--c--contextuals--border--semantic--info--default);
  }
`;

const avatarButtonCss = css`
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--c--contextuals--border--semantic--neutral--default);
  border-radius: 8px;
  background-color: transparent;
  cursor: pointer;
  flex-shrink: 0;
  transition: border-color 0.15s ease;

  &:hover {
    border-color: var(--c--contextuals--border--semantic--info--default);
  }
`;

interface ModalProjectSettingsProps {
  project: ChatProject;
  onClose: () => void;
}

export const ModalProjectSettings = ({
  project,
  onClose,
}: ModalProjectSettingsProps) => {
  const { showToast } = useToast();
  const { t } = useTranslation();

  const { colorsTokens } = useCunninghamTheme();
  const iconColorModal = useOwnModal();

  const [name, setName] = useState(project.title);
  const [icon, setIcon] = useState(project.icon || 'folder');
  const [color, setColor] = useState(project.color || 'color_1');
  const [instructions, setInstructions] = useState(
    project.llm_instructions || '',
  );

  const IconComp = PROJECT_ICONS[icon] ?? PROJECT_ICONS.folder;
  const iconColor =
    colorsTokens[PROJECT_COLORS[color] as keyof typeof colorsTokens] ??
    undefined;

  const { mutate: updateProject, isPending } = useUpdateProject({
    onSuccess: () => {
      showToast(
        'success',
        t('The project has been updated.'),
        undefined,
        4000,
      );
      onClose();
    },
    onError: (error) => {
      const errorMessage =
        error.cause?.[0] ||
        error.message ||
        t('An error occurred while updating the project');
      showToast('error', errorMessage, undefined, 4000);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;

    updateProject({
      projectId: project.id,
      title: trimmedName,
      icon,
      color,
      llm_instructions: instructions.trim() || undefined,
    });
  };

  return (
    <>
      <Modal
        isOpen
        closeOnClickOutside
        onClose={onClose}
        aria-label={t('Project settings')}
        rightActions={
          <>
            <Button
              aria-label={t('Close the modal')}
              color="brand"
              variant="bordered"
              onClick={onClose}
            >
              {t('Cancel')}
            </Button>
            <Button
              aria-label={t('Save project settings')}
              color="brand"
              variant="primary"
              type="submit"
              form="project-settings-form"
              disabled={!name.trim() || isPending}
            >
              {t('Save')}
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
            {t('Project settings')}
          </Text>
        }
      >
        <Box className="--conversations--modal-project-settings">
          <form
            onSubmit={handleSubmit}
            id="project-settings-form"
            data-testid="project-settings-form"
            className="mt-s"
          >
            <Box $gap="base" $direction="column">
              <Box $gap="xs" $direction="column">
                <Text $size="sm" $variation="600" $weight="500">
                  {t('Project avatar and name')}
                </Text>
                <Box $direction="row" $align="center" $gap="sm">
                  <Box
                    as="button"
                    type="button"
                    $css={avatarButtonCss}
                    onClick={iconColorModal.open}
                    aria-label={t('Choose icon and color')}
                  >
                    <Box
                      $display="flex"
                      $align="center"
                      style={{ color: iconColor }}
                    >
                      <IconComp
                        width={24}
                        height={24}
                        style={{ fill: 'currentColor' }}
                      />
                    </Box>
                  </Box>
                  <Box $css="flex: 1; min-width: 0;">
                    <Input
                      type="text"
                      label={t('Project name')}
                      maxLength={100}
                      value={name}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setName(e.target.value)
                      }
                      required
                    />
                  </Box>
                </Box>
              </Box>

              <Box $gap="xs" $direction="column">
                <Text $size="sm" $variation="600" $weight="500">
                  {t('Instructions (experimental)')}
                </Text>
                <Box
                  as="textarea"
                  $css={textareaCss}
                  value={instructions}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setInstructions(e.target.value)
                  }
                  placeholder={t(
                    'Example: Be concise and maintain a professional tone.',
                  )}
                />
                <Text $size="xs" $variation="500">
                  {t(
                    'Use this field to provide any additional context the Assistant may need. This feature is being tested. It may not work as expected.',
                  )}
                </Text>
              </Box>
            </Box>
          </form>
        </Box>
      </Modal>
      {iconColorModal.isOpen && (
        <ModalIconColorPicker
          icon={icon}
          color={color}
          onIconChange={setIcon}
          onColorChange={setColor}
          onClose={iconColorModal.close}
        />
      )}
    </>
  );
};
