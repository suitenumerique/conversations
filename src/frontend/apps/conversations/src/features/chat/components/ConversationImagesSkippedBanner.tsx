import { Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';

interface ConversationImagesSkippedBannerProps {
  names: string[];
  onDismiss: () => void;
  topOffsetPx?: number;
}

export const ConversationImagesSkippedBanner = ({
  names,
  onDismiss,
  topOffsetPx = 0,
}: ConversationImagesSkippedBannerProps) => {
  const { t } = useTranslation();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const warningColor =
    'var(--c--contextuals--content--semantic--warning--primary)';

  return (
    <Box
      data-testid="conversation-images-skipped-banner"
      role="status"
      $direction="row"
      $align="center"
      $justify="space-between"
      $gap="6px"
      $margin={{ horizontal: 'auto', bottom: 'xs' }}
      $padding={{ vertical: '4px', horizontal: 'xs' }}
      $width="100%"
      $css={`
        margin-top: ${topOffsetPx > 0 ? `${topOffsetPx}px` : 'var(--c--theme--spacings--xs, 4px)'};
        max-width: var(--chat-content-max-width, 750px);
        border-radius: 6px;
        background: var(--c--contextuals--background--semantic--warning--tertiary);
        border: 1px solid var(--c--contextuals--border--semantic--warning--primary);
      `}
    >
      <Text $size="xs" $color={warningColor}>
        {t(
          "Some images in this conversation aren't being used because the current model can't read images.",
        )}
      </Text>
      <Box $direction="row" $align="center" $gap="2px">
        <button
          type="button"
          onClick={() => setDetailsOpen(true)}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            padding: '2px 6px',
            fontSize: '0.75rem',
            color: warningColor,
            textDecoration: 'underline',
          }}
        >
          {t('See details')}
        </button>
        <button
          type="button"
          aria-label={t('Dismiss')}
          onClick={onDismiss}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            padding: '2px 6px',
            fontSize: '0.75rem',
            color: warningColor,
          }}
        >
          {t('Dismiss')}
        </button>
      </Box>
      <Modal
        isOpen={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        title={t('Ignored images')}
        closeOnClickOutside={true}
        closeOnEsc={true}
        size={ModalSize.MEDIUM}
      >
        <Box
          as="ul"
          data-testid="conversation-images-skipped-details"
          $margin={{ all: 'none' }}
          $padding={{ left: 'md' }}
        >
          {names.map((name, idx) => (
            <Text key={name + idx} as="li" $size="sm">
              {name}
            </Text>
          ))}
        </Box>
      </Modal>
    </Box>
  );
};
