import { Button } from '@openfun/cunningham-react';
import React, { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, BoxButton, Icon, Text } from '@/components';
import { useResponsiveStore } from '@/stores';

interface InputChatProps {
  messagesLength: number;
  input: string | null;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  status: string | null;
  files: FileList | null;
  setFiles: React.Dispatch<React.SetStateAction<FileList | null>>;
}

export const InputChat = ({
  messagesLength,
  input,
  handleInputChange,
  handleSubmit,
  status,
  files,
  setFiles,
}: InputChatProps) => {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const { isDesktop } = useResponsiveStore();

  return (
    <Box
      $css={`
      position: sticky;
      bottom: 0;
      width: 100%;
      min-width: 80%;
      max-width: 700px;
      margin: auto;
    `}
    >
      {/* Message de bienvenue */}
      {messagesLength === 0 && (
        <Box
          $padding={{ all: 'base' }}
          $background="white"
          $radius="md"
          $align="center"
          $margin={{ horizontal: 'base', bottom: 'base', top: '-80px' }}
        >
          <Text as="h2" $size="xl" $weight="600" $margin={{ bottom: 'xs' }}>
            {t('What is on your mind?')}
          </Text>
        </Box>
      )}

      {/* Formulaire d'envoi */}
      <form
        onSubmit={handleSubmit}
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
          $direction="row"
          $align="center"
          $padding={{ bottom: 'base' }}
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
                  : '1px solid var(--c--theme--colors--greyscale-200)'
              };
            `}
          >
            <textarea
              value={input ?? ''}
              placeholder={t('Ask a question')}
              onChange={handleInputChange}
              disabled={status !== 'ready'}
              rows={1}
              style={{
                width: '100%',
                padding: '1rem 1.5rem',
                background: 'transparent',
                outline: 'none',
                fontSize: '1rem',
                border: 'none',
                resize: 'none',
                fontFamily: 'inherit',
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit?.();
                }
              }}
            />

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
                $direction="row"
                $gap="2"
                $margin={{ horizontal: 'base', bottom: 'xs', top: 'xs' }}
              >
                {Array.from(files).map((file, idx) => {
                  const { type: _type, name } = file;
                  const removeFile = () => {
                    const dt = new DataTransfer();
                    Array.from(files).forEach((f, i) => {
                      if (i !== idx) {
                        dt.items.add(f);
                      }
                    });
                    setFiles(dt.files.length > 0 ? dt.files : null);
                  };

                  return (
                    <Box
                      key={name + idx}
                      $direction="column"
                      $align="center"
                      $gap="xs"
                    >
                      {/*{type.startsWith('image/') ? (
                  <Image
                    style={{ width: 96, borderRadius: 8 }}
                    src={URL.createObjectURL(file)}
                    alt={name}
                    width={96}
                    height={96}
                  />
                ) : (
                  <Box
                    $background="var(--c--theme--colors--greyscale-100)"
                    $width="64px"
                    $height="80px"
                    $radius="md"
                  />
                )}*/}
                      <Box
                        $background="var(--c--theme--colors--greyscale-050)"
                        $width="200px"
                        $direction="row"
                        $align="center"
                        $padding="xs"
                        $css={`
                    border: 1px solid var(--c--theme--colors--greyscale-200);
                    border-radius: 8px;
      
                  `}
                      >
                        <Text
                          $size="sm"
                          $color="var(--c--theme--colors--greyscale-850)"
                          $css={`
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: initial;
                    display: -webkit-box;
                    line-clamp: 1;
                    -webkit-line-clamp: 1;
                    -webkit-box-orient: vertical;
                    `}
                        >
                          {name}
                        </Text>
                        <BoxButton
                          aria-label="Remove file"
                          onClick={removeFile}
                        >
                          <Icon
                            iconName="close"
                            $theme="greyscale"
                            $size="18px"
                          />
                        </BoxButton>
                      </Box>
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
                  onClick={() => fileInputRef.current?.click()}
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
                <Button
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
                </Button>
              </Box>
              <Box $padding={{ horizontal: 'sm' }}>
                <Button
                  size="small"
                  aria-label="Send"
                  disabled={!input || !input.trim()}
                  icon={
                    <Icon
                      $variation="800"
                      $theme="primary-text"
                      iconName={
                        status === 'ready' ? 'arrow_upward' : 'crop_square'
                      }
                    />
                  }
                >
                  {status !== 'ready' && <Text>Stop</Text>}
                </Button>
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
