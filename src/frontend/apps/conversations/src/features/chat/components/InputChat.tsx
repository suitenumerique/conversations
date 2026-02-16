import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';
import { useToast } from '@/components/ToastProvider';
import { FeatureFlagState, useConfig } from '@/core';
import { LLMModel } from '@/features/chat/api/useLLMConfiguration';
import { InputChatActions } from '@/features/chat/components/InputChatAction';
import { SuggestionCarousel } from '@/features/chat/components/SuggestionCarousel';
import { WelcomeMessage } from '@/features/chat/components/WelcomeMessage';
import { useFileDragDrop } from '@/features/chat/hooks/useFileDragDrop';
import { useFileUrls } from '@/features/chat/hooks/useFileUrls';
import { useAnalytics } from '@/libs';
import { useResponsiveStore } from '@/stores';

import FilesIcon from '../assets/files.svg';

import { AttachmentList } from './AttachmentList';
import { ScrollDown } from './ScrollDown';

interface InputChatProps {
  messagesLength: number;
  input: string | null;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  status: string | null;
  files: FileList | null;
  setFiles: React.Dispatch<React.SetStateAction<FileList | null>>;
  onScrollToBottom?: () => void;
  containerRef?: React.RefObject<HTMLDivElement | null>;
  forceWebSearch?: boolean;
  onToggleWebSearch?: () => void;
  onStop?: () => void;
  selectedModel?: LLMModel | null;
  onModelSelect?: (model: LLMModel) => void;
  isUploadingFiles?: boolean;
}

const STYLES = {
  form: { width: '100%' },
  formPadding: { bottom: 'base' },
  formPaddingMobile: { bottom: '' },
  attachmentMargin: { horizontal: '0', bottom: 'xs', top: 'xs' },
  attachmentPadding: { horizontal: 'base' },
  horizontalPadding: { horizontal: 'base' },
} as const;

const CONTAINER_CSS = `
  display: block;
  position: relative;
  margin: auto;
  width: 100%;
  max-width: 750px;
`;

const INPUT_BOX_CSS = `
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  border: 1px solid var(--c--contextuals--border--surface--primary);
  position: relative;
  background: var(--c--contextuals--background--surface--primary);
  transition: all 0.2s ease;
  `;

const FILE_DROP_CSS = `
                top: -1px; left: -1px;
                border-radius: 12px;
                z-index: 1001;
                background-color: var(--c--contextuals--background--semantic--brand--tertiary);
                width: 100%;
                height: 100%;
                outline: 2px solid var(--c--contextuals--border--semantic--brand--secondary);
                box-shadow: 0 0 64px 0 rgba(62, 93, 231, 0.25);
                `;
const DRAG_FADE_CSS = `
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            animation: fadeIn 0.3s;
            z-index: 999;
            background-color: rgba(255, 255, 255, 0.1);
            pointer-events: all;
          `;

const TEXTAREA_STYLE: React.CSSProperties = {
  padding: '1rem 1.5rem 0.5rem 1.5rem',
  background: 'transparent',
  outline: 'none',
  fontSize: '1rem',
  border: 'none',
  resize: 'none',
  fontFamily: 'inherit',
  minHeight: '64px',
  maxHeight: '200px',
  overflowY: 'auto',
  transition: 'all 0.2s ease',
  borderRadius: '12px',
  color: 'var(--c--theme--colors--greyscale-800)',
  lineHeight: '1.5',
};
const SCROLL_DOWN_WRAPPER_CSS = `
  position: relative;
  height: 0;
  width: 100%;
  margin: auto;
  max-width: 750px;
`;
export const InputChat = ({
  messagesLength,
  input,
  handleInputChange,
  handleSubmit,
  status,
  files,
  setFiles,
  onScrollToBottom,
  containerRef,
  forceWebSearch = false,
  onToggleWebSearch,
  onStop,
  selectedModel,
  onModelSelect,
  isUploadingFiles = false,
}: InputChatProps) => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { isDesktop, isMobile } = useResponsiveStore();

  const { data: conf } = useConfig();
  const { isFeatureFlagActivated } = useAnalytics();
  const [fileUploadEnabled, setFileUploadEnabled] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);

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

  const showToastError = useCallback(() => {
    showToast(
      'error',
      `${t('File type not supported')}`,
      undefined,
      undefined,
      {
        actionLabel: t('Know more'),
        actionHref:
          'https://docs.numerique.gouv.fr/docs/060b7b70-15aa-4d9a-86f5-2d31c3d693d5/',
      },
    );
  }, [showToast, t]);

  useEffect(() => {
    if (!conf?.FEATURE_FLAGS) {
      setWebSearchEnabled(false);
      setFileUploadEnabled(false);
      return;
    }
    const isFeatureEnabled = (featureKey: string): boolean => {
      const configValue = conf.FEATURE_FLAGS[featureKey];
      if (!configValue) {
        return false;
      } else if (configValue === FeatureFlagState.DISABLED) {
        return false;
      } else if (configValue === FeatureFlagState.ENABLED) {
        return true;
      } else {
        return isFeatureFlagActivated(featureKey);
      }
    };

    setWebSearchEnabled(isFeatureEnabled('web-search'));
    setFileUploadEnabled(isFeatureEnabled('document-upload'));
  }, [conf, isFeatureFlagActivated]);

  useEffect(() => {
    if (textareaRef.current && messagesLength === 0 && status === 'ready') {
      textareaRef.current.focus();
    }
  }, [messagesLength, status]);

  useEffect(() => {
    if (textareaRef.current && status === 'ready' && !input) {
      textareaRef.current.focus();
    }
  }, [status, input]);

  const validateAndAddFiles = useCallback(
    (filesToAdd: File[]) => {
      const acceptedFiles: File[] = [];
      const rejectedFiles: File[] = [];

      filesToAdd.forEach((file) => {
        if (isFileAccepted(file)) {
          acceptedFiles.push(file);
        } else {
          rejectedFiles.push(file);
        }
      });

      if (rejectedFiles.length > 0) {
        showToastError();
      }

      if (acceptedFiles.length > 0) {
        setFiles((prev) => {
          const dt = new DataTransfer();

          // Keep existing files
          if (prev) {
            Array.from(prev).forEach((f) => dt.items.add(f));
          }

          // Add new files (avoiding duplicates)
          acceptedFiles.forEach((f) => {
            const isDuplicate = Array.from(prev || []).some(
              (pf) =>
                pf.name === f.name &&
                pf.size === f.size &&
                pf.lastModified === f.lastModified,
            );
            if (!isDuplicate) {
              dt.items.add(f);
            }
          });

          return dt.files;
        });
      }
    },
    [isFileAccepted, showToastError, setFiles],
  );

  const { isDragActive } = useFileDragDrop({
    enabled: fileUploadEnabled,
    isFileAccepted,
    onFilesAccepted: validateAndAddFiles,
    onFilesRejected: () => showToastError(),
  });

  const isInputDisabled = status !== 'ready' || isUploadingFiles;

  const containerCss = useMemo(
    () => `
  ${CONTAINER_CSS}
  padding: ${isDesktop ? '0' : '0 10px'};
`,
    [isDesktop],
  );

  const textareaStyle = useMemo(
    () => ({
      ...TEXTAREA_STYLE,
      opacity: status === 'error' ? '0.5' : '1',
    }),
    [status],
  );

  const formPadding = isDesktop ? STYLES.formPadding : STYLES.formPaddingMobile;

  // handlers
  const handleTextareaChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      handleInputChange(e);
      const textarea = e.target;
      textarea.style.height = 'auto';
      const newHeight = Math.min(textarea.scrollHeight, 200);
      textarea.style.height = `${newHeight}px`;
    },
    [handleInputChange],
  );

  const handleTextareaKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        const textarea = e.target as HTMLTextAreaElement;
        textarea.style.height = '0';
        e.currentTarget.form?.requestSubmit?.();
      }
    },
    [],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      if (!fileUploadEnabled) {
        return;
      }

      const clipboardData = e.clipboardData;
      if (!clipboardData) {
        return;
      }

      // Due to browser limitations, only one file can be pasted at a time
      // Check files first (for files from file system)
      let file: File | null = null;

      if (clipboardData.files && clipboardData.files.length > 0) {
        file = clipboardData.files[0];
      } else if (clipboardData.items) {
        for (let i = 0; i < clipboardData.items.length; i++) {
          const item = clipboardData.items[i];
          if (item.kind === 'file') {
            file = item.getAsFile();
            break;
          }
        }
      }

      if (file) {
        e.preventDefault();
        validateAndAddFiles([file]);
      }
    },
    [fileUploadEnabled, validateAndAddFiles],
  );

  const handleAttachClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleWebSearchToggle = useCallback(() => {
    onToggleWebSearch?.();
    textareaRef.current?.focus();
  }, [onToggleWebSearch]);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList) {
        return;
      }

      validateAndAddFiles(Array.from(fileList));
      e.target.value = '';
    },
    [validateAndAddFiles],
  );

  const handleAttachmentRemove = useCallback(
    (index: number) => {
      if (!files) {
        return;
      }

      const dt = new DataTransfer();
      Array.from(files).forEach((f, i) => {
        if (i !== index) {
          dt.items.add(f);
        }
      });
      setFiles(dt.files.length > 0 ? dt.files : null);
    },
    [files, setFiles],
  );

  const fileUrlMap = useFileUrls(files);

  const attachments = useMemo(() => {
    if (!files) {
      return [];
    }

    return Array.from(files).map((file) => {
      const key = `${file.name}-${file.size}-${file.lastModified}`;
      return {
        name: file.name,
        contentType: file.type,
        url: fileUrlMap.get(key) || '',
      };
    });
  }, [files, fileUrlMap]);

  return (
    <>
      {isDragActive && <Box $position="fixed" $css={DRAG_FADE_CSS} />}
      <Box $css={containerCss}>
        {/* Bouton de scroll vers le bas */}
        {messagesLength > 1 && containerRef && onScrollToBottom && (
          <Box $css={SCROLL_DOWN_WRAPPER_CSS}>
            <ScrollDown
              onClick={onScrollToBottom}
              containerRef={containerRef}
            />
          </Box>
        )}
        {/* Message de bienvenue */}
        {messagesLength === 0 && <WelcomeMessage />}

        <form onSubmit={handleSubmit} style={STYLES.form}>
          <Box $padding={formPadding}>
            <Box
              $flex={1}
              $radius="12px"
              $position="relative"
              $background="white"
              $css={INPUT_BOX_CSS}
            >
              {isDragActive && (
                <Box
                  $position="absolute"
                  $align="center"
                  $direction="row"
                  $justify="center"
                  $gap="1rem"
                  $css={FILE_DROP_CSS}
                >
                  <FilesIcon />
                  <Box>
                    <Text
                      $weight="700"
                      $color="var(--c--contextuals--border--semantic--brand--primary)"
                    >
                      {t('Add file')}
                    </Text>
                    <Text
                      $weight="400"
                      $color="var(--c--contextuals--border--semantic--brand--primary)"
                    >
                      {t('To add a file to the conversation, drop it here.')}
                    </Text>
                  </Box>
                </Box>
              )}
              <textarea
                ref={textareaRef}
                aria-label={t('Enter your message or a question')}
                value={input ?? ''}
                name="inputchat-textarea"
                onChange={handleTextareaChange}
                onKeyDown={handleTextareaKeyDown}
                onPaste={handlePaste}
                disabled={isInputDisabled}
                rows={1}
                style={textareaStyle}
              />

              {!input && <SuggestionCarousel messagesLength={messagesLength} />}

              <input
                accept={conf?.chat_upload_accept}
                type="file"
                multiple
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={handleFileChange}
              />
              {/*Aperçu des fichiers*/}
              {files && files.length > 0 && (
                <Box
                  $margin={STYLES.attachmentMargin}
                  $padding={STYLES.attachmentPadding}
                >
                  <AttachmentList
                    attachments={attachments}
                    onRemove={handleAttachmentRemove}
                    isReadOnly={false}
                  />
                </Box>
              )}
              <InputChatActions
                fileUploadEnabled={fileUploadEnabled}
                webSearchEnabled={webSearchEnabled}
                isUploadingFiles={isUploadingFiles}
                isMobile={isMobile}
                forceWebSearch={forceWebSearch}
                onAttachClick={handleAttachClick}
                onWebSearchToggle={
                  onToggleWebSearch ? handleWebSearchToggle : undefined
                }
                onModelSelect={onModelSelect}
                selectedModel={selectedModel || null}
                status={status}
                inputHasContent={Boolean(input?.trim())}
                onStop={onStop}
              />
            </Box>
          </Box>
        </form>
      </Box>
    </>
  );
};
