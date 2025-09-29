import { Button } from '@openfun/cunningham-react';
import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { FeatureFlagState, useConfig } from '@/core';
import { useAnalytics } from '@/libs';
import { useResponsiveStore } from '@/stores';

import { AttachmentList } from './AttachmentList';
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
}: InputChatProps) => {
  const { t } = useTranslation();
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

  const suggestions = [
    t('Ask a question'),
    t('Turn this list into bullet points'),
    t('Write a short product description'),
    t('Find recent news about...'),
  ];

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

  return (
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
      {messagesLength > 1 &&
        status !== 'streaming' &&
        containerRef &&
        onScrollToBottom && (
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
          $background="white"
          $align="center"
          $margin={{ horizontal: 'base', bottom: 'md', top: '0' }}
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
          setIsDragActive(false);
          if (!fileUploadEnabled) {
            return;
          }
          if (e.dataTransfer.files?.length) {
            setFiles((prev) => {
              const dt = new DataTransfer();
              if (prev) {
                Array.from(prev).forEach((f) => dt.items.add(f));
              }
              Array.from(e.dataTransfer.files).forEach((f) => {
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
        }}
        style={{ width: '100%' }}
      >
        <Box
          $padding={{ bottom: `${isDesktop ? 'base' : ''}` }}
          $background="white"
        >
          <Box
            $flex={1}
            $css={`
              box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.05);
              border-radius: 0.5rem;
              border: ${
                isDragActive
                  ? '2px dashed var(--c--theme--colors--primary-400)'
                  : '1px solid var(--c--theme--colors--greyscale-100)'
              };
              position: relative;
            `}
          >
            <textarea
              ref={textareaRef}
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
              disabled={status !== 'ready'}
              rows={1}
              style={{
                padding: '1rem 1.5rem',
                background: 'transparent',
                outline: 'none',
                fontSize: '1rem',
                border: 'none',
                resize: 'none',
                fontFamily: 'inherit',
                minHeight: '60px',
                maxHeight: '200px',
                overflowY: 'auto',
                transition: 'all 0.3s cubic-bezier(1, 0, 0, 1)',
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
                  color: var(--c--theme--colors--greyscale-500);
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
                  {[...suggestions, suggestions[0]].map((suggestion, index) => (
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
                  ))}
                </Box>
              </Box>
            )}

            <input
              type="file"
              multiple
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={(e) => {
                const fileList = e.target.files;
                if (!fileList) {
                  return;
                }
                setFiles((prev) => {
                  const dt = new DataTransfer();
                  if (prev) {
                    Array.from(prev).forEach((f: File) => dt.items.add(f));
                  }
                  Array.from(fileList).forEach((f: File) => {
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
            >
              <Box $flex="1" $direction="row" $padding={{ horizontal: 'base' }}>
                <Button
                  size="small"
                  type="button"
                  disabled={!fileUploadEnabled}
                  onClick={() => fileInputRef.current?.click()}
                  aria-label={t('Add attach file')}
                  className="c__button--neutral attach-file-button"
                  icon={
                    <Icon
                      iconName="attach_file"
                      $theme="greyscale"
                      $variation="550"
                      $size={`${isMobile ? '24px' : '16px'}`}
                    />
                  }
                >
                  {!isMobile && (
                    <Text $theme="greyscale" $variation="550" $weight="500">
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
                        background-color: var(--c--theme--colors--primary-100) !important;
                      }
                    `
                          : ''
                      }
                    `}
                  >
                    <Button
                      size="small"
                      type="button"
                      disabled={!webSearchEnabled}
                      onClick={onToggleWebSearch}
                      aria-label={t('Research on the web')}
                      className="c__button--neutral research-web-button"
                      icon={
                        <Icon
                          iconName="language"
                          $theme="greyscale"
                          $variation="550"
                          $css={`
                            color: ${forceWebSearch ? 'var(--c--theme--colors--primary-600) !important' : 'var(--c--theme--colors--greyscale-600)'}
                          `}
                        />
                      }
                    >
                      {!isMobile && (
                        <Text
                          $theme={forceWebSearch ? 'primary' : 'greyscale'}
                          $variation="550"
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
                            $theme="primary"
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
                            $variation="text"
                            $theme="primary"
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
              <Box $padding={{ horizontal: 'sm' }}>
                <SendButton
                  status={status}
                  disabled={!input || !input.trim()}
                  onClick={onStop}
                />
              </Box>
            </Box>
          </Box>
        </Box>
      </form>
    </Box>
  );
};
