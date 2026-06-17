import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';

// Define Attachment type locally (mirroring backend structure)
export interface Attachment {
  name?: string;
  contentType?: string;
  url: string;
  // Stamped by the backend when an attachment was kept on the persisted message
  // but excluded from what the model saw (e.g. an image on a text-only model).
  // The renderer surfaces an inline "removed" chip when this is set.
  skipped?: { reason: string } | null;
}

interface AttachmentListProps {
  attachments: Attachment[];
  onRemove?: (index: number) => void;
  isReadOnly?: boolean;
}

export const AttachmentList = ({
  attachments,
  onRemove,
  isReadOnly = false,
}: AttachmentListProps) => {
  const { t } = useTranslation();

  if (!attachments || attachments.length === 0) {
    return null;
  }

  return (
    <Box
      $direction={isReadOnly ? 'column' : 'row'}
      $align={isReadOnly ? 'flex-end' : ''}
      $margin={{ bottom: 'md' }}
      $gap="0.5rem"
      $width="100%"
      $css={`
        overflow-x: auto;
      `}
    >
      {attachments.map((attachment, idx) => {
        const { name } = attachment;
        const isSkipped = Boolean(attachment.skipped);
        const removeAttachment = () => {
          if (onRemove) {
            onRemove(idx);
          }
        };
        if (!name) {
          return null;
        }
        const chipBackground = isSkipped
          ? 'var(--c--contextuals--background--semantic--warning--tertiary)'
          : 'var(--c--contextuals--background--semantic--neutral--tertiary)';
        return (
          <Box
            key={(name || 'attachment') + idx}
            $direction="column"
            $align={isReadOnly ? 'flex-end' : 'center'}
            $gap="2px"
          >
            <Box
              $background={chipBackground}
              $width="200px"
              $direction="row"
              $gap="8px"
              $align="center"
              $padding={{ all: '4px', left: 'xs' }}
              $css={`
                border-radius: 4px;
              `}
              data-testid={isSkipped ? 'attachment-skipped-chip' : undefined}
            >
              {/* Extension du fichier */}
              <Box
                $background="var(--c--contextuals--background--palette--gray--primary)"
                $width="22px"
                $height="22px"
                $direction="row"
                $align="center"
                $justify="center"
                $css={`
                  flex-shrink: 0;
                  border-radius: 8px;
                `}
              >
                <Text
                  $color="var(--c--contextuals--content--semantic--overlay--primary)"
                  $weight="500"
                  $css={`
                    font-size: 7px;
                  `}
                >
                  {name?.split('.').pop()?.toUpperCase() || 'FILE'}
                </Text>
              </Box>
              <Text
                $size="xs"
                $variation="500"
                $color="var(--c--contextuals--content--semantic--neutral--primary)"
                $css={`
                  overflow: hidden;
                  text-overflow: ellipsis;
                  white-space: initial;
                  display: -webkit-box;
                  line-clamp: 1;
                  -webkit-line-clamp: 1;
                  -webkit-box-orient: vertical;
                  flex: 1;
                  text-decoration: ${isSkipped ? 'line-through' : 'none'};
                `}
              >
                {name}
              </Text>
              {!isReadOnly && onRemove && (
                <Button
                  color="neutral"
                  variant="tertiary"
                  size="small"
                  className="c__button--without-padding"
                  tabIndex={0}
                  aria-label={t('Remove attachment')}
                  onClick={removeAttachment}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      removeAttachment();
                    }
                  }}
                >
                  <Icon iconName="close" $size="18px" />
                </Button>
              )}
            </Box>
            {isSkipped && (
              <Text
                $size="xs"
                $color="var(--c--contextuals--content--semantic--warning--primary)"
                $css="max-width: 200px; text-align: right;"
              >
                {t('Image not analyzed. Try again later.')}
              </Text>
            )}
          </Box>
        );
      })}
    </Box>
  );
};
