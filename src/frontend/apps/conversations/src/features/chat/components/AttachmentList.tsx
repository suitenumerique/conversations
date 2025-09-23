import { Box, BoxButton, Icon, Text } from '@/components';

// Define Attachment type locally (mirroring backend structure)
export interface Attachment {
  name?: string;
  contentType?: string;
  url: string;
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
  if (!attachments || attachments.length === 0) {
    return null;
  }

  return (
    <Box
      $direction="row"
      $gap="0.5rem"
      $width="100%"
      $css={`
        overflow-x: scroll;
      `}
    >
      {attachments.map((attachment, idx) => {
        const { name } = attachment;
        const removeAttachment = () => {
          if (onRemove) {
            onRemove(idx);
          }
        };
        if (!name) {
          return null;
        }
        return (
          <Box
            key={(name || 'attachment') + idx}
            $direction="column"
            $align="center"
          >
            <Box
              $background="var(--c--theme--colors--greyscale-050)"
              $minWidth="200px"
              $direction="row"
              $gap="xs"
              $align="center"
              $padding="xs"
              $css={`
                border-radius: 4px;
              `}
            >
              {/* Extension du fichier */}
              <Box
                $background="var(--c--theme--colors--greyscale-200)"
                $width="24px"
                $height="24px"
                $direction="row"
                $align="center"
                $margin={{ right: 'xs' }}
                $justify="center"
                $css={`
                  flex-shrink: 0;
                  border-radius: 4px;
                `}
              >
                <Text
                  $color="var(--c--theme--colors--greyscale-700)"
                  $weight="500"
                  $css={`
                    font-size: 8px;
                  `}
                >
                  {name?.split('.').pop()?.toUpperCase() || 'FILE'}
                </Text>
              </Box>
              <Text
                $size="xs"
                $color="var(--c--theme--colors--greyscale-850)"
                $css={`
                  overflow: hidden;
                  text-overflow: ellipsis;
                  white-space: initial;
                  display: -webkit-box;
                  line-clamp: 1;
                  -webkit-line-clamp: 1;
                  -webkit-box-orient: vertical;
                  flex: 1;
                `}
              >
                {name}
              </Text>
              {!isReadOnly && onRemove && (
                <BoxButton
                  aria-label="Remove attachment"
                  onClick={removeAttachment}
                >
                  <Icon iconName="close" $theme="greyscale" $size="18px" />
                </BoxButton>
              )}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
};
