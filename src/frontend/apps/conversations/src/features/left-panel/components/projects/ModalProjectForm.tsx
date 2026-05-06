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
  const { mutate: deleteAttachment, mutateAsync: deleteAttachmentAsync } =
    useDeleteProjectAttachment(project?.id ?? '');

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

  // Per-project caps for files and images (server-enforced; surfaced here so
  // the UI rejects over-cap uploads immediately rather than waiting for a 400).
  // Companion markdown rows from the server side are excluded from `existingAttachments`
  // by the project-attachments listing endpoint, so a simple split by content_type
  // matches the server-side counting rule.
  const filesMaxCount = conf?.project_files_max_count;
  const imagesMaxCount = conf?.project_images_max_count;
  const isImage = (contentType?: string) =>
    typeof contentType === 'string' && contentType.startsWith('image/');
  const currentImagesCount =
    (existingAttachments?.filter((att) => isImage(att.content_type)).length ??
      0) + form.files.filter((f) => isImage(f.type)).length;
  const currentFilesCount =
    (existingAttachments?.filter((att) => !isImage(att.content_type)).length ??
      0) + form.files.filter((f) => !isImage(f.type)).length;

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
        // Drop the file from the local form list too: the toast tells the
        // user it failed, and leaving the entry behind would block re-adding
        // the same name (findConflict treats it as a duplicate), eat from
        // the per-project caps, and show in the list with no failure cue —
        // edit-mode submit doesn't re-upload form.files, so it'd be dropped
        // silently anyway. User retries by re-picking the file.
        dispatch({ type: 'REMOVE_FILE_BY_NAME', name: file.name });
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
  // Names accepted in the current picker batch — form.files won't reflect them
  // synchronously after dispatch, so we track them here to detect duplicates
  // selected together in the same picker.
  const batchAcceptedNamesRef = useRef<Set<string>>(new Set());

  const processNextFile = useCallback(() => {
    while (pendingFilesRef.current.length > 0) {
      const file = pendingFilesRef.current.shift()!; // eslint-disable-line @typescript-eslint/no-non-null-assertion
      let found = findConflict(file);
      if (!found && batchAcceptedNamesRef.current.has(file.name)) {
        // Same name already accepted earlier in this batch — the original is
        // dispatched but not yet in form.files. Resolve index lazily at confirm.
        found = { file };
      }
      if (found) {
        setConflict(found);
        setConflictChoice('replace');
        return; // wait for user choice
      }
      batchAcceptedNamesRef.current.add(file.name);
      addFilesToForm([file]);
    }
    batchAcceptedNamesRef.current.clear();
  }, [findConflict, addFilesToForm]);

  // Filters a batch through type-acceptance + per-project image/file caps,
  // emitting the same toasts whether the batch came from the file picker or
  // from drag-and-drop. Caps are tracked locally as the batch is processed so
  // a single batch of N items cannot all sneak past the current counts.
  //
  // Files whose name matches an existing attachment (server-side or pending
  // local) skip the cap check here: the conflict resolver decides their fate.
  // Replace doesn't change category counts, and Keep Both re-runs this helper
  // on the renamed file so the cap is enforced exactly once at the right time.
  const enforceProjectUploadCaps = useCallback(
    (files: File[]): File[] => {
      const accepted: File[] = [];
      const existingNames = new Set([
        ...(existingAttachments?.map((att) => att.file_name) ?? []),
        ...form.files.map((f) => f.name),
      ]);
      let imagesAllowance =
        imagesMaxCount !== undefined
          ? Math.max(imagesMaxCount - currentImagesCount, 0)
          : Infinity;
      let filesAllowance =
        filesMaxCount !== undefined
          ? Math.max(filesMaxCount - currentFilesCount, 0)
          : Infinity;

      files.forEach((file) => {
        if (!isFileAccepted(file)) {
          showToast('error', t('File type not supported'), undefined, 4000);
          return;
        }
        if (existingNames.has(file.name)) {
          accepted.push(file);
          return;
        }
        if (isImage(file.type)) {
          if (imagesAllowance <= 0) {
            showToast(
              'error',
              t(
                'This project is at the maximum number of images. Remove one before uploading another.',
              ),
              undefined,
              4000,
            );
            return;
          }
          imagesAllowance -= 1;
        } else {
          if (filesAllowance <= 0) {
            showToast(
              'error',
              t(
                'This project is at the maximum number of files. Remove one before uploading another.',
              ),
              undefined,
              4000,
            );
            return;
          }
          filesAllowance -= 1;
        }
        accepted.push(file);
      });

      return accepted;
    },
    [
      isFileAccepted,
      showToast,
      t,
      imagesMaxCount,
      filesMaxCount,
      currentImagesCount,
      currentFilesCount,
      existingAttachments,
      form.files,
    ],
  );

  const handleConflictConfirm = useCallback(async () => {
    if (!conflict) return;

    if (conflictChoice === 'replace') {
      if (conflict.existingAttachmentId) {
        // Server attachment: await the DELETE so the subsequent upload can't
        // race the cleanup and re-collide on the same filename server-side.
        try {
          await deleteAttachmentAsync(conflict.existingAttachmentId);
        } catch {
          showToast('error', t('Failed to replace file'), undefined, 4000);
          setConflict(null);
          processNextFile();
          return;
        }
        void uploadFileImmediately(conflict.file);
        setConflict(null);
        processNextFile();
        return;
      } else {
        // Existing local file: index was either captured at conflict time
        // (form-level) or must be looked up now (in-batch duplicate, where the
        // prior copy was dispatched after conflict creation and is now in form).
        const idx =
          conflict.existingLocalIndex ??
          form.files.findIndex((f) => f.name === conflict.file.name);
        if (idx >= 0) {
          // In-batch duplicate guard: if the original is still uploading,
          // dispatching REPLACE_LOCAL_FILE + a second uploadFileImmediately
          // would race two uploads on the same name; the original's
          // REMOVE_FILE_BY_NAME would then wipe the replacement's form slot.
          // Skip and let the user retry once the in-flight upload completes.
          if (uploadingFiles.has(conflict.file.name)) {
            showToast(
              'warning',
              t(
                '"{{name}}" is still uploading - retry replacement once it completes.',
                { name: conflict.file.name },
              ),
              undefined,
              4000,
            );
            setConflict(null);
            processNextFile();
            return;
          }
          dispatch({
            type: 'REPLACE_LOCAL_FILE',
            index: idx,
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
      }
    } else {
      const newName = deduplicateFileName(
        conflict.file.name,
        getAllFileNames(),
      );
      const renamed = new File([conflict.file], newName, {
        type: conflict.file.type,
      });
      // Keep Both creates a new file: re-run cap enforcement now that the
      // rename has cleared the conflict-skip path. If over cap, the helper
      // toasts and we drop this file before continuing the batch.
      const allowed = enforceProjectUploadCaps([renamed]);
      if (allowed.length > 0) {
        addFilesToForm(allowed);
      }
    }

    setConflict(null);
    processNextFile();
  }, [
    conflict,
    conflictChoice,
    deleteAttachmentAsync,
    form.files,
    getAllFileNames,
    processNextFile,
    addFilesToForm,
    enforceProjectUploadCaps,
    isEditing,
    uploadFileImmediately,
    uploadingFiles,
    showToast,
    t,
  ]);

  const addFilesWithConflictCheck = useCallback(
    (files: File[]) => {
      pendingFilesRef.current = files;
      batchAcceptedNamesRef.current = new Set();
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

      const accepted = enforceProjectUploadCaps(Array.from(fileList));
      if (accepted.length > 0) {
        addFilesWithConflictCheck(accepted);
      }
      e.target.value = '';
    },
    [enforceProjectUploadCaps, addFilesWithConflictCheck],
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
              const accepted = enforceProjectUploadCaps(
                Array.from(droppedFiles),
              );
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
                      {form.files
                        .map((file, idx) => ({ file, idx }))
                        // Hide local rows whose name has already landed in
                        // existingAttachments: between the post-upload refetch
                        // and the REMOVE_FILE_BY_NAME dispatch, both can be
                        // present for a frame and would render as a duplicate.
                        .filter(
                          ({ file }) =>
                            !existingAttachments?.some(
                              (att) => att.file_name === file.name,
                            ),
                        )
                        .map(({ file, idx }) => {
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
                  batchAcceptedNamesRef.current.clear();
                }}
              >
                {t('Cancel')}
              </Button>
              <Button
                color="brand"
                variant="primary"
                onClick={() => void handleConflictConfirm()}
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
