import { Button } from '@openfun/cunningham-react';
import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, BoxButton, Icon, Text } from '@/components';
import { useResponsiveStore } from '@/stores';

import { ScrollDown } from './ScrollDown';
import { SendButton } from './SendButton';

interface InputChatProps {
  messagesLength: number;
  input: string | null;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void | Promise<void>;
  status: string | null;
  files: FileList | null;
  setFiles: React.Dispatch<React.SetStateAction<FileList | null>>;
  onScrollToBottom?: () => void;
  containerRef?: React.RefObject<HTMLDivElement | null>;
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
  onStop,
}: InputChatProps) => {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const { isDesktop } = useResponsiveStore();
  const [currentSuggestionIndex, setCurrentSuggestionIndex] = useState(0);

  const suggestions = [
    'Turn this list into bullet points',
    'Write a short product description',
    'Find recent news about...',
    'Ask a question',
  ];

  useEffect(() => {
    if (messagesLength === 0) {
      const interval = setInterval(() => {
        setCurrentSuggestionIndex((prev) => (prev + 1) % suggestions.length);
      }, 3000);

      return () => clearInterval(interval);
    }
  }, [messagesLength, suggestions.length]);

  return (
    <Box
      $css={`
      display: block;
      position: relative;
      margin: auto;
      width: 100%;
      padding: ${isDesktop ? '0' : '0 10px'};
      max-width: 750px;
      @keyframes fadeIn {
        from {
          opacity: 0;
        }
        to {
          opacity: 1;
        }
      }
      @keyframes fadeInDown {
        from {
          opacity: 0;
          transform: translateY(-20px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
      @keyframes slideOutToBottom {
        from {
          opacity: 1;
          transform: translateY(0);
        }
        to {
          opacity: 0;
          transform: translateY(20px);
        }
      }
    `}
    >
      {/* Bouton de scroll vers le bas */}
      {messagesLength > 1 && containerRef && onScrollToBottom && (
        <Box
          $css={`
            position: relative;
            bottom: 0;
            width: 100%;
            margin: auto;
            max-width: 750px;
        `}
        >
          <ScrollDown onClick={onScrollToBottom} containerRef={containerRef} />
        </Box>
      )}
      {/* Message de bienvenue */}
      {messagesLength === 0 && (
        <Box
          $padding={{ all: 'base', bottom: 'md' }}
          $background="white"
          $align="center"
          $margin={{ horizontal: 'base', bottom: 'md', top: '0' }}
          $css={`
            opacity: 0;
            animation: fadeIn 0.2s cubic-bezier(1,0,0,1) 0.2s both;
          `}
        >
          <Text as="h2" $size="xl" $weight="600" $margin={{ all: '0' }}>
            {t('What is on your mind?')}
          </Text>
        </Box>
      )}

      <form
        onSubmit={(event) => {
          void handleSubmit(event);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragActive(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragActive(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragActive(false);
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
          $css={
            messagesLength === 0
              ? `
            opacity: 0;
            animation: fadeIn 0.4s cubic-bezier(1,0,0,1) 0s both;
          `
              : 'animation: fadeIn 0.4s cubic-bezier(1,0,0,1) 0.4s both;'
          }
        >
          <Box
            $flex={1}
            $css={`
              box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.05);
              border-radius: 0.5rem;
              border: ${
                isDragActive
                  ? '2px dashed var(--c--theme--colors--primary-400)'
                  : '1px solid var(--c--theme--colors--greyscale-200)'
              };
              position: relative;
            `}
          >
            <textarea
              value={input ?? ''}
              name="inputchat-textarea"
              placeholder={
                messagesLength === 0
                  ? suggestions[currentSuggestionIndex]
                  : t('Ask a question')
              }
              onChange={(e) => {
                handleInputChange(e);
                const textarea = e.target;
                textarea.style.height = 'auto';
                const newHeight = Math.min(textarea.scrollHeight, 200);
                textarea.style.height = `${newHeight}px`;
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
                transition: 'all 0.3s ease',
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
                  e.preventDefault();
                  const textarea = e.target as HTMLTextAreaElement;
                  textarea.style.height = '0';
                  e.currentTarget.form?.requestSubmit?.();
                }
              }}
            />

            {messagesLength === 0 && !input && (
              <Box
                $css={`
                  position: absolute;
                  top: 1rem;
                  left: 1.5rem;
                  right: 1.5rem;
                  pointer-events: none;
                  color: var(--c--theme--colors--greyscale-500);
                  font-size: 1rem;
                  font-family: inherit;
                  line-height: 1.5;
                `}
              >
                {suggestions.map((suggestion, index) => (
                  <Box
                    key={index}
                    $css={`
                      position: absolute;
                      top: 0;
                      left: 0;
                      right: 0;
                      opacity: ${index === currentSuggestionIndex ? 1 : 0};
                      &::placeholder {
                        transition: opacity ${index === currentSuggestionIndex ? '0.4s' : '0s'};
                      }
                    `}
                  >
                    {suggestion}
                  </Box>
                ))}
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
                console.log(fileList);
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
                $direction="row"
                $gap="0.5rem"
                $width="100%"
                $css={`
                  overflow-x: auto;
                  overflow-y: hidden;
                  scrollbar-width: thin;
                  scrollbar-color: var(--c--theme--colors--greyscale-300) transparent;
                  &::-webkit-scrollbar {
                    height: 4px;
                  }
                  &::-webkit-scrollbar-track {
                    background: transparent;
                    margin: 0 4px;
                  }
                  &::-webkit-scrollbar-thumb {
                    background: var(--c--theme--colors--greyscale-300);
                    border-radius: 3px;
                  }
                  &::-webkit-scrollbar-thumb:hover {
                    background: var(--c--theme--colors--greyscale-400);
                  }
                `}
                $margin={{ horizontal: '0', top: 'xs' }}
                $padding={{ horizontal: 'base', bottom: 'sm' }}
              >
                {Array.from(files).map((file, idx) => {
                  const { name } = file;
                  const removeFile = () => {
                    const dt = new DataTransfer();
                    Array.from(files).forEach((f, i) => {
                      if (i !== idx) {
                        dt.items.add(f);
                      }
                    });
                    setFiles(dt.files.length > 0 ? dt.files : null);
                  };

                  // Fonction pour obtenir l'extension
                  const getFileExtension = (fileName: string) => {
                    const parts = fileName.split('.');
                    return parts.length > 1
                      ? parts[parts.length - 1].toUpperCase()
                      : '';
                  };

                  const fileExtension = getFileExtension(name);

                  return (
                    <Box
                      key={name + idx}
                      $direction="row"
                      $align="center"
                      $gap="md"
                      $css={`
                          background: var(--c--theme--colors--greyscale-050);
                          border-radius: 8px;
                          padding: 8px 12px;
                          min-width: 0;
                          max-width: 200px;
                          flex-shrink: 0;
                        `}
                    >
                      {/* Extension du fichier */}
                      <Box
                        $css={`
                          width: 24px;
                          height: 24px;
                          border-radius: 4px;
                          background: var(--c--theme--colors--primary-100);
                          display: flex;
                          align-items: center;
                          justify-content: center;
                          flex-shrink: 0;
                          font-weight: 600;
                          font-size: 10px;
                          color: var(--c--theme--colors--primary-700);
                          margin-right: 8px;
                        `}
                      >
                        {fileExtension}
                      </Box>

                      {/* Nom du fichier */}
                      <div
                        style={{
                          fontSize: '14px',
                          color: 'var(--c--theme--colors--greyscale-850)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                          maxWidth: '160px',
                          lineHeight: 1,
                          textAlign: 'left',
                          paddingLeft: '4px',
                        }}
                      >
                        {name}
                      </div>

                      <BoxButton
                        aria-label="Remove file"
                        onClick={removeFile}
                        $css={`
                          flex-shrink: 0;
                        `}
                      >
                        <Icon
                          iconName="close"
                          $theme="greyscale"
                          $size="16px"
                        />
                      </BoxButton>
                    </Box>
                  );
                })}
              </Box>
            )}
            <Box
              $flex="1"
              $direction="row"
              $padding={{ bottom: 'base' }}
              $align="space-between"
            >
              <Box $flex="1" $direction="row" $padding={{ horizontal: 'base' }}>
                <Button
                  size="small"
                  type="button"
                  onClick={(e: React.MouseEvent) => {
                    e.preventDefault();
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                  aria-label={t('Add attach file')}
                  color="tertiary-text"
                  icon={
                    <Icon
                      iconName="attach_file"
                      $theme="greyscale"
                      $variation="600"
                      $size="24px"
                    />
                  }
                >
                  {isDesktop && <Text $weight="500">{t('Attach file')}</Text>}
                </Button>
                {/*<Button
                  size="small"
                  onClick={() => fileInputRef.current?.click()}
                  aria-label={t('Research on the web')}
                  color="tertiary-text"
                  icon={
                    <Icon
                      iconName="language"
                      $theme="greyscale"
                      $variation="600"
                      $size="24px"
                    />
                  }
                >
                  {isDesktop && (
                    <Text $weight="500">{t('Research on the web')}</Text>
                  )}
                </Button>*/}
              </Box>
              <Box $padding={{ horizontal: 'sm' }}>
                <SendButton
                  status={status}
                  disabled={!input || !input.trim()}
                  onClick={() => {
                    if (onStop) {
                      onStop();
                    }
                  }}
                />
              </Box>
            </Box>
          </Box>
        </Box>
      </form>
    </Box>

    /*          <DropdownMenu
            options={[
              {
                icon: 'attach_file',
                label: 'Attach files',
                callback: () => fileInputRef.current?.click(),
              },
            ]}
          >
            <Icon
              iconName="attach_file"
              $theme="primary"
              $variation="800"
              $size="24px"
            />
          </DropdownMenu>*/
  );
};
