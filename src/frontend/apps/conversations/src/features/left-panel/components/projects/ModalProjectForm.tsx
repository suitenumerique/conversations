import {
  Button,
  Input,
  Loader,
  Modal,
  ModalSize,
  TextArea,
} from '@gouvfr-lasuite/cunningham-react';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useReducer, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import FileDocIcon from '@/assets/icons/uikit-custom/file-doc.svg';
import FileGenericIcon from '@/assets/icons/uikit-custom/file-filled.svg';
import FileImageIcon from '@/assets/icons/uikit-custom/file-image.svg';
import FilePdfIcon from '@/assets/icons/uikit-custom/file-pdf.svg';
import { Box, DropButton, Icon, Text, useToast } from '@/components';
import { FeatureFlagState, useConfig } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { uploadProjectFiles } from '@/features/attachments/api/uploadProjectFiles';
import { useDeleteProjectAttachment } from '@/features/attachments/api/useDeleteProjectAttachment';
import {
  KEY_PROJECT_ATTACHMENTS,
  useProjectAttachments,
} from '@/features/attachments/api/useProjectAttachments';
import { useCreateProject } from '@/features/chat/api/useCreateProject';
import { useUpdateProject } from '@/features/chat/api/useUpdateProject';
import { ChatProject } from '@/features/chat/types';

import { ModalIconColorPicker } from './ModalIconColorPicker';
import { PROJECT_COLORS, PROJECT_ICONS } from './project-constants';

const getFileIcon = (contentTypeOrName: string) => {
  const ct = contentTypeOrName.toLowerCase();
  if (ct === 'application/pdf' || ct.endsWith('.pdf')) return FilePdfIcon;
  if (ct.startsWith('image/') || /\.(png|jpe?g|gif|svg|webp)$/i.test(ct))
    return FileImageIcon;
  if (
    ct.includes('word') ||
    ct.includes('document') ||
    ct.includes('text/') ||
    ct.includes('spreadsheet') ||
    ct.includes('presentation') ||
    /\.(docx?|xlsx?|pptx?|odt|ods|odp|txt|csv|md)$/i.test(ct)
  )
    return FileDocIcon;
  return FileGenericIcon;
};

/**
 * Generate a unique file name by appending a number before the extension.
 * e.g. "report.pdf" -> "report 2.pdf", "report 3.pdf", ...
 */
const deduplicateFileName = (name: string, existingNames: string[]): string => {
  const dotIdx = name.lastIndexOf('.');
  const base = dotIdx > 0 ? name.slice(0, dotIdx) : name;
  const ext = dotIdx > 0 ? name.slice(dotIdx) : '';

  let counter = 2;
  let candidate = `${base} ${counter}${ext}`;
  while (existingNames.includes(candidate)) {
    counter++;
    candidate = `${base} ${counter}${ext}`;
  }
  return candidate;
};

interface FileConflict {
  file: File;
  existingAttachmentId?: string; // set if conflict is with a server attachment
  existingLocalIndex?: number; // set if conflict is with a pending local file
}

interface FormState {
  name: string;
  icon: string;
  color: string;
  instructions: string;
  files: File[];
}

type FormAction =
  | { type: 'SET_NAME'; value: string }
  | { type: 'SET_ICON'; value: string }
  | { type: 'SET_COLOR'; value: string }
  | { type: 'SET_INSTRUCTIONS'; value: string }
  | { type: 'ADD_FILES'; value: File[] }
  | { type: 'REMOVE_FILE'; index: number }
  | { type: 'REPLACE_LOCAL_FILE'; index: number; file: File }
  | { type: 'REMOVE_FILE_BY_NAME'; name: string };

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
    case 'ADD_FILES':
      return { ...state, files: [...state.files, ...action.value] };
    case 'REMOVE_FILE':
      return {
        ...state,
        files: state.files.filter((_, i) => i !== action.index),
      };
    case 'REPLACE_LOCAL_FILE':
      return {
        ...state,
        files: state.files.map((f, i) =>
          i === action.index ? action.file : f,
        ),
      };
    case 'REMOVE_FILE_BY_NAME':
      return {
        ...state,
        files: state.files.filter((f) => f.name !== action.name),
      };
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
  const queryClient = useQueryClient();

  const { colorsTokens } = useCunninghamTheme();

  const { data: conf } = useConfig();
  const fileUploadEnabled =
    conf?.FEATURE_FLAGS?.['document-upload'] === FeatureFlagState.ENABLED;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: existingAttachments } = useProjectAttachments(project?.id);
  const { mutate: deleteAttachment } = useDeleteProjectAttachment(
    project?.id ?? '',
  );

  const [form, dispatch] = useReducer(formReducer, {
    name: project?.title ?? '',
    icon: project?.icon || 'folder',
    color: project?.color || 'color_6',
    instructions: project?.llm_instructions || '',
    files: [],
  });

  const isFileAccepted = useCallback(
    (file: File): boolean => {
      const acceptedConfig = conf?.chat_upload_accept;
      if (!acceptedConfig) {
        return true;
      }
      const acceptedTypes = acceptedConfig
        .split(',')
        .map((type) => type.trim());
      return acceptedTypes.some((acceptedType) => {
        if (acceptedType.startsWith('.')) {
          return file.name.toLowerCase().endsWith(acceptedType.toLowerCase());
        }
        if (acceptedType.endsWith('/*')) {
          const baseType = acceptedType.slice(0, -2);
          return file.type.startsWith(baseType);
        }
        return file.type === acceptedType;
      });
    },
    [conf?.chat_upload_accept],
  );

  const [conflict, setConflict] = useState<FileConflict | null>(null);
  const [conflictChoice, setConflictChoice] = useState<'replace' | 'keep'>(
    'replace',
  );
  const [uploadingFiles, setUploadingFiles] = useState<Set<string>>(new Set());
  const isUploading = uploadingFiles.size > 0;

  const uploadFileImmediately = useCallback(
    async (file: File) => {
      if (!project?.id) return;
      setUploadingFiles((prev) => new Set(prev).add(file.name));
      try {
        await uploadProjectFiles(project.id, [file], conf?.FILE_UPLOAD_MODE);
        await queryClient.invalidateQueries({
          queryKey: [KEY_PROJECT_ATTACHMENTS, project.id],
        });
        dispatch({ type: 'REMOVE_FILE_BY_NAME', name: file.name });
      } catch {
        showToast('error', t('Failed to upload file'), undefined, 4000);
      } finally {
        setUploadingFiles((prev) => {
          const next = new Set(prev);
          next.delete(file.name);
          return next;
        });
      }
    },
    [project?.id, conf?.FILE_UPLOAD_MODE, queryClient, showToast, t],
  );

  const addFilesToForm = useCallback(
    (files: File[]) => {
      dispatch({ type: 'ADD_FILES', value: files });
      if (isEditing) {
        for (const file of files) {
          void uploadFileImmediately(file);
        }
      }
    },
    [isEditing, uploadFileImmediately],
  );

  const getAllFileNames = useCallback((): string[] => {
    const serverNames = existingAttachments?.map((att) => att.file_name) ?? [];
    const localNames = form.files.map((f) => f.name);
    return [...serverNames, ...localNames];
  }, [existingAttachments, form.files]);

  const findConflict = useCallback(
    (file: File): FileConflict | null => {
      const serverMatch = existingAttachments?.find(
        (att) => att.file_name === file.name,
      );
      if (serverMatch) {
        return { file, existingAttachmentId: serverMatch.id };
      }
      const localIdx = form.files.findIndex((f) => f.name === file.name);
      if (localIdx >= 0) {
        return { file, existingLocalIndex: localIdx };
      }
      return null;
    },
    [existingAttachments, form.files],
  );

  // Queue of files waiting to be processed (for multi-file conflict resolution)
  const pendingFilesRef = useRef<File[]>([]);

  const processNextFile = useCallback(() => {
    while (pendingFilesRef.current.length > 0) {
      const file = pendingFilesRef.current.shift()!; // eslint-disable-line @typescript-eslint/no-non-null-assertion
      const found = findConflict(file);
      if (found) {
        setConflict(found);
        setConflictChoice('replace');
        return; // wait for user choice
      }
      addFilesToForm([file]);
    }
  }, [findConflict, addFilesToForm]);

  const handleConflictConfirm = useCallback(() => {
    if (!conflict) return;

    if (conflictChoice === 'replace') {
      if (conflict.existingAttachmentId) {
        deleteAttachment(conflict.existingAttachmentId);
      } else if (conflict.existingLocalIndex !== undefined) {
        dispatch({
          type: 'REPLACE_LOCAL_FILE',
          index: conflict.existingLocalIndex,
          file: conflict.file,
        });
        if (isEditing) {
          void uploadFileImmediately(conflict.file);
        }
        setConflict(null);
        processNextFile();
        return;
      }
      addFilesToForm([conflict.file]);
    } else {
      const newName = deduplicateFileName(
        conflict.file.name,
        getAllFileNames(),
      );
      const renamed = new File([conflict.file], newName, {
        type: conflict.file.type,
      });
      addFilesToForm([renamed]);
    }

    setConflict(null);
    processNextFile();
  }, [
    conflict,
    conflictChoice,
    deleteAttachment,
    getAllFileNames,
    processNextFile,
    addFilesToForm,
    isEditing,
    uploadFileImmediately,
  ]);

  const addFilesWithConflictCheck = useCallback(
    (files: File[]) => {
      pendingFilesRef.current = files;
      processNextFile();
    },
    [processNextFile],
  );

  const handleAddFiles = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList) return;

      const accepted: File[] = [];
      Array.from(fileList).forEach((file) => {
        if (isFileAccepted(file)) {
          accepted.push(file);
        } else {
          showToast('error', t('File type not supported'), undefined, 4000);
        }
      });

      if (accepted.length > 0) {
        addFilesWithConflictCheck(accepted);
      }
      e.target.value = '';
    },
    [isFileAccepted, showToast, t, addFilesWithConflictCheck],
  );

  const IconComp = PROJECT_ICONS[form.icon] ?? PROJECT_ICONS.folder;
  const colorToken = PROJECT_COLORS[form.color];
  const iconColor = colorToken
    ? (colorsTokens[colorToken as keyof typeof colorsTokens] ?? undefined)
    : undefined;

  const { mutateAsync: createProjectAsync, isPending: isCreating } =
    useCreateProject();

  const { mutateAsync: updateProjectAsync, isPending: isUpdating } =
    useUpdateProject();

  const isPending = isCreating || isUpdating;

  const uploadFilesSequentially = async (projectId: string, files: File[]) => {
    for (const file of files) {
      setUploadingFiles((prev) => new Set(prev).add(file.name));
      try {
        await uploadProjectFiles(projectId, [file], conf?.FILE_UPLOAD_MODE);
      } catch {
        showToast('error', t('Failed to upload file'), undefined, 4000);
      } finally {
        setUploadingFiles((prev) => {
          const next = new Set(prev);
          next.delete(file.name);
          return next;
        });
      }
    }
    void queryClient.invalidateQueries({
      queryKey: [KEY_PROJECT_ATTACHMENTS, projectId],
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
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
      try {
        await updateProjectAsync({ projectId: project.id, ...payload });
        showToast(
          'success',
          t('The project has been updated.'),
          undefined,
          4000,
        );
        onClose();
      } catch (error) {
        const err = error as { cause?: string[]; message?: string };
        const errorMessage =
          err.cause?.[0] ||
          err.message ||
          t('An error occurred while updating the project');
        showToast('error', errorMessage, undefined, 4000);
      }
    } else {
      try {
        const created = await createProjectAsync(payload);

        if (form.files.length > 0) {
          await uploadFilesSequentially(created.id, form.files);
        }

        showToast(
          'success',
          t('The project has been created.'),
          undefined,
          4000,
        );
        onClose();
      } catch (error) {
        const err = error as { cause?: string[]; message?: string };
        const errorMessage =
          err.cause?.[0] ||
          err.message ||
          t('An error occurred while creating the project');
        showToast('error', errorMessage, undefined, 4000);
      }
    }
  };

  const formId = isEditing ? 'project-settings-form' : 'create-project-form';

  return (
    <>
      <Modal
        isOpen
        closeOnClickOutside={!isUploading}
        onClose={isUploading ? () => {} : onClose}
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
              disabled={isUploading}
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
              disabled={!form.name.trim() || isPending || isUploading}
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
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            const droppedFiles = e.dataTransfer?.files;
            if (droppedFiles && droppedFiles.length > 0) {
              const accepted: File[] = [];
              Array.from(droppedFiles).forEach((file) => {
                if (isFileAccepted(file)) {
                  accepted.push(file);
                }
              });
              if (accepted.length > 0) {
                addFilesWithConflictCheck(accepted);
              }
            }
          }}
        >
          <form
            onSubmit={(e) => void handleSubmit(e)}
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
                    dispatch({
                      type: 'SET_INSTRUCTIONS',
                      value: e.target.value,
                    })
                  }
                  placeholder={t(
                    'Example: Be concise and maintain a professional tone.',
                  )}
                />
              </Box>

              {fileUploadEnabled && (
                <Box $direction="column" $margin={{ top: 'base' }}>
                  <Box
                    $direction="row"
                    $align="center"
                    $justify="space-between"
                    $margin={{ bottom: 'xxs' }}
                  >
                    <Text $size="sm" $theme="neutral" $weight="500">
                      {t('Files')}
                    </Text>
                    <Button
                      color="neutral"
                      variant="bordered"
                      size="small"
                      onClick={handleAddFiles}
                      type="button"
                      icon={<Icon iconName="add" $size="16px" />}
                    >
                      {t('Add files')}
                    </Button>
                  </Box>
                  <Text
                    $size="sm"
                    $theme="neutral"
                    $variation="secondary"
                    $margin={{ bottom: 'xs' }}
                  >
                    {t(
                      'Add your files to the project so the Assistant can use them as a resource.',
                    )}
                  </Text>

                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept={conf?.chat_upload_accept}
                    onChange={handleFileChange}
                    style={{ display: 'none' }}
                  />

                  {(existingAttachments?.length ?? 0) > 0 ||
                  form.files.length > 0 ? (
                    <Box
                      $direction="column"
                      $css={`
                    border: 1px solid var(--c--contextuals--border--semantic--neutral--tertiary);
                    border-radius: 4px;
                    max-height: 175px;
                    overflow-y: auto;
                  `}
                    >
                      {existingAttachments?.map((att) => {
                        const AttIcon = getFileIcon(att.content_type);
                        return (
                          <Box
                            key={att.id}
                            $direction="row"
                            $align="center"
                            $gap="8px"
                            $padding={{ vertical: 'xs', horizontal: 'sm' }}
                            $css={`
                        border-bottom: 1px solid var(--c--contextuals--border--semantic--neutral--tertiary);
                        &:last-child { border-bottom: none; }
                      `}
                          >
                            <AttIcon width={24} height={24} />
                            <Text
                              $size="sm"
                              $css="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;"
                            >
                              {att.file_name}
                            </Text>
                            <Button
                              color="neutral"
                              variant="tertiary"
                              size="small"
                              className="c__button--without-padding"
                              aria-label={t('Remove attachment')}
                              type="button"
                              onClick={() => deleteAttachment(att.id)}
                            >
                              <Icon iconName="close" $size="18px" />
                            </Button>
                          </Box>
                        );
                      })}
                      {form.files.map((file, idx) => {
                        const FileIcon = getFileIcon(file.name);
                        const fileIsUploading = uploadingFiles.has(file.name);
                        return (
                          <Box
                            key={'new-' + file.name + idx}
                            $direction="row"
                            $align="center"
                            $gap="8px"
                            $padding={{ vertical: 'xs', horizontal: 'sm' }}
                            $css={`
                        border-bottom: 1px solid var(--c--contextuals--border--semantic--neutral--tertiary);
                        &:last-child { border-bottom: none; }
                      `}
                          >
                            <FileIcon width={24} height={24} />
                            <Text
                              $size="sm"
                              $css="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;"
                            >
                              {file.name}
                            </Text>
                            {fileIsUploading ? (
                              <Loader size="small" />
                            ) : (
                              <Button
                                color="neutral"
                                variant="tertiary"
                                size="small"
                                className="c__button--without-padding"
                                aria-label={t('Remove attachment')}
                                type="button"
                                onClick={() =>
                                  dispatch({
                                    type: 'REMOVE_FILE',
                                    index: idx,
                                  })
                                }
                              >
                                <Icon iconName="close" $size="18px" />
                              </Button>
                            )}
                          </Box>
                        );
                      })}
                    </Box>
                  ) : (
                    <Box
                      $align="center"
                      $justify="center"
                      $padding={{ all: 'sm' }}
                      $css={`
                    border: 1px dashed var(--c--contextuals--border--semantic--neutral--tertiary);
                    border-radius: 4px;
                    cursor: pointer;
                  `}
                      onClick={handleAddFiles}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleAddFiles();
                        }
                      }}
                    >
                      <Text $size="sm" $theme="primary">
                        {t('Add file')}
                      </Text>
                    </Box>
                  )}
                </Box>
              )}
            </Box>
          </form>
        </Box>
      </Modal>

      {conflict && (
        <Modal
          isOpen
          closeOnClickOutside
          onClose={() => {
            setConflict(null);
            pendingFilesRef.current = [];
          }}
          aria-label={t('File already exists')}
          size={ModalSize.SMALL}
          rightActions={
            <>
              <Button
                color="brand"
                variant="bordered"
                onClick={() => {
                  setConflict(null);
                  pendingFilesRef.current = [];
                }}
              >
                {t('Cancel')}
              </Button>
              <Button
                color="brand"
                variant="primary"
                onClick={handleConflictConfirm}
              >
                {t('Import')}
              </Button>
            </>
          }
          title={
            <Box $direction="column" $gap="4px">
              <Text $size="h6" as="h6" $margin={{ all: '0' }} $variation="1000">
                {t('File already exists')}
              </Text>
              <Text $size="sm" $theme="neutral" $variation="secondary">
                {t('How would you like to proceed?')}
              </Text>
            </Box>
          }
        >
          <Box $direction="column" $gap="16px" $padding={{ vertical: 'sm' }}>
            <Box
              $direction="row"
              $align="center"
              $gap="12px"
              $css="cursor: pointer;"
              role="radio"
              aria-checked={conflictChoice === 'replace'}
              tabIndex={0}
              onClick={() => setConflictChoice('replace')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setConflictChoice('replace');
                }
              }}
            >
              <input
                type="radio"
                name="conflict-choice"
                checked={conflictChoice === 'replace'}
                readOnly
                tabIndex={-1}
              />
              <Text $size="sm">{t('Replace existing file')}</Text>
            </Box>
            <Box
              $direction="row"
              $align="center"
              $gap="12px"
              $css="cursor: pointer;"
              role="radio"
              aria-checked={conflictChoice === 'keep'}
              tabIndex={0}
              onClick={() => setConflictChoice('keep')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setConflictChoice('keep');
                }
              }}
            >
              <input
                type="radio"
                name="conflict-choice"
                checked={conflictChoice === 'keep'}
                readOnly
                tabIndex={-1}
              />
              <Text $size="sm">{t('Keep both files')}</Text>
            </Box>
          </Box>
        </Modal>
      )}
    </>
  );
};
