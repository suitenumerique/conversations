import {
  Button,
  Input,
  Modal,
  ModalSize,
  TextArea,
} from '@gouvfr-lasuite/cunningham-react';
import { useReducer } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, DropButton, Text, useToast } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useCreateProject } from '@/features/chat/api/useCreateProject';
import { useUpdateProject } from '@/features/chat/api/useUpdateProject';
import { ChatProject } from '@/features/chat/types';

import { ModalIconColorPicker } from './ModalIconColorPicker';
import { PROJECT_COLORS, PROJECT_ICONS } from './project-constants';

interface FormState {
  name: string;
  icon: string;
  color: string;
  instructions: string;
}

type FormAction =
  | { type: 'SET_NAME'; value: string }
  | { type: 'SET_ICON'; value: string }
  | { type: 'SET_COLOR'; value: string }
  | { type: 'SET_INSTRUCTIONS'; value: string };

const formReducer = (state: FormState, action: FormAction): FormState => {
  switch (action.type) {
    case 'SET_NAME':
      return { ...state, name: action.value };
    case 'SET_ICON':
      return { ...state, icon: action.value };
    case 'SET_COLOR':
      return { ...state, color: action.value };
    case 'SET_INSTRUCTIONS':
      return { ...state, instructions: action.value };
  }
};

const avatarButtonCss = css`
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--c--contextuals--border--semantic--neutral--tertiary);
  border-radius: 4px;
  background-color: transparent;
  cursor: pointer;
  flex-shrink: 0;
  transition: border-color 0.15s ease;
`;

interface ModalProjectFormProps {
  project?: ChatProject;
  onClose: () => void;
}

export const ModalProjectForm = ({
  project,
  onClose,
}: ModalProjectFormProps) => {
  const isEditing = !!project;
  const { showToast } = useToast();
  const { t } = useTranslation();

  const { colorsTokens } = useCunninghamTheme();

  const [form, dispatch] = useReducer(formReducer, {
    name: project?.title ?? '',
    icon: project?.icon || 'folder',
    color: project?.color || 'color_6',
    instructions: project?.llm_instructions || '',
  });

  const IconComp = PROJECT_ICONS[form.icon] ?? PROJECT_ICONS.folder;
  const colorToken = PROJECT_COLORS[form.color];
  const iconColor = colorToken
    ? (colorsTokens[colorToken as keyof typeof colorsTokens] ?? undefined)
    : undefined;

  const { mutate: createProject, isPending: isCreating } = useCreateProject({
    onSuccess: () => {
      showToast('success', t('The project has been created.'), undefined, 4000);
      onClose();
    },
    onError: (error) => {
      const errorMessage =
        error.cause?.[0] ||
        error.message ||
        t('An error occurred while creating the project');
      showToast('error', errorMessage, undefined, 4000);
    },
  });

  const { mutate: updateProject, isPending: isUpdating } = useUpdateProject({
    onSuccess: () => {
      showToast('success', t('The project has been updated.'), undefined, 4000);
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

  const isPending = isCreating || isUpdating;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = form.name.trim();
    if (!trimmedName) return;

    const payload = {
      title: trimmedName,
      icon: form.icon,
      color: form.color,
      llm_instructions: form.instructions.trim(),
    };

    if (isEditing) {
      updateProject({ projectId: project.id, ...payload });
    } else {
      createProject(payload);
    }
  };

  const formId = isEditing ? 'project-settings-form' : 'create-project-form';

  return (
    <Modal
      isOpen
      closeOnClickOutside
      onClose={onClose}
      aria-label={
        isEditing
          ? t('Project settings')
          : t('Content modal to create a project')
      }
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
            aria-label={
              isEditing ? t('Save project settings') : t('Create project')
            }
            color="brand"
            variant="primary"
            type="submit"
            form={formId}
            disabled={!form.name.trim() || isPending}
          >
            {isEditing ? t('Save') : t('Create project')}
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
          {isEditing ? t('Project settings') : t('New project')}
        </Text>
      }
    >
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <Box
        className={
          isEditing
            ? '--conversations--modal-project-settings'
            : '--conversations--modal-create-project'
        }
        onKeyDown={(e) => e.stopPropagation()}
      >
        <form
          onSubmit={handleSubmit}
          id={formId}
          data-testid={formId}
          className="mt-s"
        >
          <Box $direction="column">
            <Box $direction="column" $gap="8px" $margin={{ bottom: 'base' }}>
              <Text $size="sm" $theme="neutral" $weight="500">
                {t('Avatar and name')}
              </Text>
              <Box $direction="row" $align="top" $gap="8px" $height="42px">
                <DropButton
                  button={
                    <Box $css={avatarButtonCss} style={{ color: iconColor }}>
                      <IconComp
                        width={24}
                        height={24}
                        style={{ fill: 'currentColor' }}
                      />
                    </Box>
                  }
                  label={t('Choose icon and color')}
                >
                  <ModalIconColorPicker
                    icon={form.icon}
                    color={form.color}
                    onIconChange={(value) =>
                      dispatch({ type: 'SET_ICON', value })
                    }
                    onColorChange={(value) =>
                      dispatch({ type: 'SET_COLOR', value })
                    }
                  />
                </DropButton>

                <Box $width="100%" $height="40px">
                  <Input
                    className="inputName__text"
                    type="text"
                    aria-label={t('Project name')}
                    maxLength={100}
                    value={form.name}
                    fullWidth
                    placeholder={t('Project name')}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      dispatch({ type: 'SET_NAME', value: e.target.value })
                    }
                    required
                  />
                </Box>
              </Box>
            </Box>

            <Box $direction="column">
              <Text
                $size="sm"
                $theme="neutral"
                $weight="500"
                $margin={{ bottom: 'xs' }}
              >
                {t('Instructions (experimental)')}
              </Text>
              <Text
                $size="sm"
                $theme="neutral"
                $variation="secondary"
                $margin={{ bottom: 'xxs' }}
              >
                {t(
                  'Use this field to provide any additional context the Assistant may need. This feature is being tested. It may not work as expected.',
                )}
              </Text>
              <TextArea
                aria-label={t('Instructions (experimental)')}
                rows={6}
                maxLength={4000} // cf. backend LLM_INSTRUCTIONS_MAX_LENGTH
                value={form.instructions}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                  dispatch({ type: 'SET_INSTRUCTIONS', value: e.target.value })
                }
                placeholder={t(
                  'Example: Be concise and maintain a professional tone.',
                )}
              />
            </Box>
          </Box>
        </form>
      </Box>
    </Modal>
  );
};
