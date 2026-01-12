import { Button } from '@openfun/cunningham-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { useToast } from '@/components/ToastProvider';
import { FeatureFlagState, useConfig } from '@/core';
import { LLMModel } from '@/features/chat/api/useLLMConfiguration';
import { useAnalytics } from '@/libs';
import { useResponsiveStore } from '@/stores';

import FilesIcon from '../assets/files.svg';

import { AttachmentList } from './AttachmentList';
import { ModelSelector } from './ModelSelector';
import { ScrollDown } from './ScrollDown';
import { SendButton } from './SendButton';

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
  const [isDragActive, setIsDragActive] = useState(false);
  const { isDesktop, isMobile } = useResponsiveStore();
  const [currentSuggestionIndex, setCurrentSuggestionIndex] = useState(0);
  const { data: conf } = useConfig();
  const { isFeatureFlagActivated } = useAnalytics();
  const [fileUploadEnabled, setFileUploadEnabled] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

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

  const suggestions = [
    t('Ask a question'),
    t('Turn this list into bullet points'),
    t('Write a short product description'),
    t('Find recent news about...'),
  ];

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
    if (messagesLength === 0) {
      const interval = setInterval(() => {
        setCurrentSuggestionIndex((prev) => {
          if (prev === suggestions.length - 1) {
            return suggestions.length;
          }
          return prev + 1;
        });
      }, 3000);

      return () => clearInterval(interval);
    }
  }, [messagesLength, suggestions.length]);

  useEffect(() => {
    if (currentSuggestionIndex === suggestions.length) {
      const timeout = setTimeout(() => {
        setIsResetting(true);
        setCurrentSuggestionIndex(0);
        setTimeout(() => setIsResetting(false), 50);
      }, 500);
      return () => clearTimeout(timeout);
    }
  }, [currentSuggestionIndex, suggestions.length]);

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

  useEffect(() => {
    if (!fileUploadEnabled) {
      return;
    }

    const handleDragEnter = (e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer?.types.includes('Files')) {
        setIsDragActive(true);
      }
    };

    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault();
      // Only hide when leaving the window completely
      if (!e.relatedTarget) {
        setIsDragActive(false);
      }
    };

    const handleDragOver = (e: DragEvent) => {
      e.preventDefault();

      // Check for rejected files during drag over (does not work on Safari)
      if (e.dataTransfer?.items) {
        const items = Array.from(e.dataTransfer.items);
        items.some((item) => {
          if (item.kind === 'file') {
            // Check file type
            const type = item.type;
            const dummyFile = new File([], '', { type });
            return !isFileAccepted(dummyFile);
          }
          return false;
        });
      }
    };

    const handleDrop = (e: DragEvent) => {
      e.preventDefault();
      setIsDragActive(false);

      if (!fileUploadEnabled) {
        return;
      }

      const droppedFiles = e.dataTransfer?.files;
      if (droppedFiles && droppedFiles.length > 0) {
        const acceptedFiles: File[] = [];
        const rejectedFiles: string[] = [];

        Array.from(droppedFiles).forEach((file) => {
          if (isFileAccepted(file)) {
            acceptedFiles.push(file);
          } else {
            rejectedFiles.push(file.name);
          }
        });

        if (rejectedFiles.length > 0) {
          showToastError();
        }

        if (acceptedFiles.length === 0) {
          return;
        }

        setFiles((prev) => {
          const dt = new DataTransfer();
          if (prev) {
            Array.from(prev).forEach((f) => dt.items.add(f));
          }
          acceptedFiles.forEach((f) => {
            if (
              !Array.from(prev || []).some(
                (pf) =>
                  pf.name === f.name &&
                  pf.size === f.size &&
                  pf.lastModified === f.lastModified,
              )
            ) {
              dt.items.add(f);
            }
          });
          return dt.files;
        });
      }
    };

    window.addEventListener('dragenter', handleDragEnter);
    window.addEventListener('dragleave', handleDragLeave);
    window.addEventListener('dragover', handleDragOver);
    window.addEventListener('drop', handleDrop);

    return () => {
      window.removeEventListener('dragenter', handleDragEnter);
      window.removeEventListener('dragleave', handleDragLeave);
      window.removeEventListener('dragover', handleDragOver);
      window.removeEventListener('drop', handleDrop);
    };
  }, [
    fileUploadEnabled,
    setFiles,
    showToastError,
    conf?.chat_upload_accept,
    isFileAccepted,
  ]);

  const isInputDisabled = status !== 'ready' || isUploadingFiles;

  return (
    <>
      {isDragActive && (
        <Box
          $position="fixed"
          $css={`
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            animation: fadeIn 0.3s;
            z-index: 999;
            background-color: rgba(255, 255, 255, 0.5);
            pointer-events: all;
          `}
        />
      )}
      <Box
        $css={`
        display: block;
        position: relative;
        margin: auto;
        width: 100%;
        padding: ${isDesktop ? '0' : '0 10px'};
        max-width: 750px;
      `}
      >
        {/* Bouton de scroll vers le bas */}
        {messagesLength > 1 && containerRef && onScrollToBottom && (
          <Box
            $css={`
            position: relative;
            height: 0;
            width: 100%;
            margin: auto;
            max-width: 750px;
          `}
          >
            <ScrollDown
              onClick={onScrollToBottom}
              containerRef={containerRef}
            />
          </Box>
        )}
        {/* Message de bienvenue */}
        {messagesLength === 0 && (
          <Box
            $padding={{ all: 'base', bottom: 'md' }}
            $align="center"
            $margin={{ horizontal: 'base', bottom: 'md', top: '-105px' }}
          >
            <Text as="h2" $size="xl" $weight="600" $margin={{ all: '0' }}>
              {t('What is on your mind?')}
            </Text>
          </Box>
        )}

        <form
          onSubmit={handleSubmit}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragActive(fileUploadEnabled);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setIsDragActive(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            // File handling is now done by global handler
          }}
          style={{ width: '100%' }}
        >
          <Box $padding={{ bottom: `${isDesktop ? 'base' : ''}` }}>
            <Box
              $flex={1}
              $radius="12px"
              $position="relative"
              $background="white"
              $css={`
              box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.08);
              border-radius: 12px;
              border: 1px solid var(--c--contextuals--border--surface--primary);
              position: relative;
              background: var(--c--contextuals--background--surface--primary,);
              transition: all 0.2s ease;
            `}
            >
              {isDragActive && (
                <Box
                  $position="absolute"
                  $align="center"
                  $direction="row"
                  $justify="center"
                  $gap="1rem"
                  $css={`
                top: -1px; left: -1px;
                border-radius: 12px;
                z-index: 1001;
                background-color: var(--c--contextuals--background--semantic--brand--tertiary);
                width: 100%;
                height: 100%;
                outline: 2px solid var(--c--contextuals--border--semantic--brand--secondary);
                box-shadow: 0 0 64px 0 rgba(62, 93, 231, 0.25);
                `}
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
                onChange={(e) => {
                  handleInputChange(e);
                  const textarea = e.target as HTMLTextAreaElement;
                  textarea.style.height = 'auto';
                  const newHeight = Math.min(textarea.scrollHeight, 200);
                  textarea.style.height = `${newHeight}px`;
                  textarea.focus();
                }}
                disabled={isInputDisabled}
                rows={1}
                style={{
                  padding: '1rem 1.5rem',
                  background: 'transparent',
                  outline: 'none',
                  fontSize: '1rem',
                  border: 'none',
                  resize: 'none',
                  opacity: status === 'error' ? '0.5' : '1',
                  fontFamily: 'inherit',
                  minHeight: '64px',
                  maxHeight: '200px',
                  overflowY: 'auto',
                  transition: 'all 0.2s ease',
                  borderRadius: '12px',
                  color: 'var(--c--theme--colors--greyscale-800)',
                  lineHeight: '1.5',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
                    e.preventDefault();
                    const textarea = e.target as HTMLTextAreaElement;
                    textarea.style.height = '0';
                    e.currentTarget.form?.requestSubmit?.();
                    textarea.focus();
                  }
                }}
              />

              {!input && (
                <Box
                  $css={`
                  position: absolute;
                  top: 1rem;
                  left: 1.5rem;
                  right: 1.5rem;
                  height: 1.5rem;
                  pointer-events: none;
                  color: var(--c--globals--colors--gray-500);
                  font-size: 1rem;
                  font-family: inherit;
                  line-height: 1.5;
                  overflow: hidden;
                `}
                >
                  <Box
                    $css={`
                    display: flex;
                    flex-direction: column;
                    height: ${(suggestions.length + 1) * 100}%;
                    transform: translateY(-${currentSuggestionIndex * (100 / (suggestions.length + 1))}%);
                    transition: ${isResetting ? 'none' : 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)'};
                  `}
                  >
                    {[...suggestions, suggestions[0]].map(
                      (suggestion, index) => (
                        <Box
                          key={index}
                          $css={`
                        height: calc(100% / ${suggestions.length + 1});
                        flex-shrink: 0;
                        white-space: nowrap;
                        display: flex;
                        justify-content: flex-start;
                      `}
                        >
                          {suggestion}
                        </Box>
                      ),
                    )}
                  </Box>
                </Box>
              )}

              <input
                accept={conf?.chat_upload_accept}
                type="file"
                multiple
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={(e) => {
                  const fileList = e.target.files;
                  if (!fileList) {
                    return;
                  }

                  const acceptedFiles: File[] = [];
                  const rejectedFiles: string[] = [];

                  Array.from(fileList).forEach((file) => {
                    if (isFileAccepted(file)) {
                      acceptedFiles.push(file);
                    } else {
                      rejectedFiles.push(file.name);
                    }
                  });

                  if (rejectedFiles.length > 0) {
                    showToastError();
                  }

                  if (acceptedFiles.length === 0) {
                    e.target.value = '';
                    return;
                  }

                  setFiles((prev) => {
                    const dt = new DataTransfer();
                    if (prev) {
                      Array.from(prev).forEach((f: File) => dt.items.add(f));
                    }
                    acceptedFiles.forEach((f: File) => {
                      if (
                        !Array.from(prev || []).some(
                          (pf) =>
                            pf.name === f.name &&
                            pf.size === f.size &&
                            pf.lastModified === f.lastModified,
                        )
                      ) {
                        dt.items.add(f);
                      }
                    });
                    return dt.files;
                  });

                  e.target.value = '';
                }}
              />
              {/*Aperçu des fichiers*/}
              {files && files.length > 0 && (
                <Box
                  $margin={{ horizontal: '0', bottom: 'xs', top: 'xs' }}
                  $padding={{ horizontal: 'base' }}
                >
                  <AttachmentList
                    attachments={Array.from(files).map((file) => ({
                      name: file.name,
                      contentType: file.type,
                      url: URL.createObjectURL(file),
                    }))}
                    onRemove={(index) => {
                      const dt = new DataTransfer();
                      Array.from(files).forEach((f, i) => {
                        if (i !== index) {
                          dt.items.add(f);
                        }
                      });
                      setFiles(dt.files.length > 0 ? dt.files : null);
                    }}
                    isReadOnly={false}
                  />
                </Box>
              )}
              <Box
                $direction="row"
                $gap="sm"
                $padding={{ bottom: 'base' }}
                $align="space-between"
                $css={`
                opacity: ${status === 'error' ? '0.5' : '1'};
                `}
              >
                <Box
                  $flex="1"
                  $direction="row"
                  $padding={{ horizontal: 'base' }}
                  $gap="xs"
                >
                  <Button
                    size="nano"
                    type="button"
                    variant="tertiary"
                    disabled={!fileUploadEnabled || isUploadingFiles}
                    onClick={() => fileInputRef.current?.click()}
                    aria-label={t('Add attach file')}
                    icon={
                      <Icon
                        iconName="attach_file"
                        $theme="neutral"
                        $variation="tertiary"
                        $size={`${isMobile ? '24px' : '16px'}`}
                      />
                    }
                  >
                    {!isMobile && (
                      <Text $variation="secondary" $theme="neutral">
                        {t('Attach file')}
                      </Text>
                    )}
                  </Button>

                  {onToggleWebSearch && (
                    <Box
                      $margin={{ left: '4px' }}
                      $css={`
                      ${
                        isMobile
                          ? `
                        .research-web-button {
                          padding-right: 8px !important;
                        }
                      `
                          : ''
                      }
                      ${
                        forceWebSearch
                          ? `
                      .research-web-button {
                        background-color: var(--c--contextuals--background--semantic--brand--secondary) !important;
                      }
                    `
                          : ''
                      }
                    `}
                    >
                      <Button
                        size="nano"
                        type="button"
                        className="research-web-button"
                        variant="tertiary"
                        disabled={!webSearchEnabled || isUploadingFiles}
                        onClick={() => {
                          onToggleWebSearch();
                          textareaRef.current?.focus();
                        }}
                        aria-label={t('Research on the web')}
                        icon={
                          <Icon
                            $theme={forceWebSearch ? 'brand' : 'neutral'}
                            $variation="tertiary"
                            iconName="language"
                          />
                        }
                      >
                        {!isMobile && (
                          <Text
                            $theme={forceWebSearch ? 'brand' : 'neutral'}
                            $variation="tertiary"
                          >
                            {t('Research on the web')}
                          </Text>
                        )}
                        {isMobile && forceWebSearch && (
                          <Box
                            $direction="row"
                            $align="space-between"
                            $gap="xs"
                            $css={`
                              display: flex;
                              align-items: center;
                              line-height: 1;
                          `}
                          >
                            <Text
                              $theme={forceWebSearch ? 'brand' : 'gray'}
                              $variation="secondary"
                              $weight="500"
                              $css={`
                                display: flex;
                                align-items: center;
                            `}
                            >
                              {t('Web')}
                            </Text>
                            <Icon
                              iconName="close"
                              $variation="secondary"
                              $theme="brand"
                              $size="md"
                              $css={`
                              display: flex;
                              align-items: center;
                              justify-content: center;
                              line-height: 1;
                              padding-left: 4px;
                            `}
                            />
                          </Box>
                        )}
                      </Button>
                    </Box>
                  )}
                </Box>
                <Box
                  $direction="row"
                  $padding={{ horizontal: 'base' }}
                  $gap="xs"
                >
                  <Box $padding={{ horizontal: 'xs' }}>
                    {onModelSelect && (
                      <ModelSelector
                        selectedModel={selectedModel || null}
                        onModelSelect={onModelSelect}
                      />
                    )}
                  </Box>

                  <SendButton
                    status={status}
                    disabled={!input || !input.trim() || isUploadingFiles}
                    onClick={onStop}
                  />
                </Box>
              </Box>
            </Box>
          </Box>
        </form>
      </Box>
    </>
  );
};
