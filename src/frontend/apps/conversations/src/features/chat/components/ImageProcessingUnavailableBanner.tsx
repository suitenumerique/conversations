import { Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import WarningFilledIcon from '@/assets/icons/uikit-custom/warning-filled.svg';
import { Box, Icon, Text } from '@/components';

interface ImageProcessingUnavailableBannerProps {
  onDismiss: () => void;
}

// Standalone rounded card sitting just above the input box.
const FLUSH_CARD_CSS = `
  margin: 0 auto;
  max-width: var(--chat-content-max-width, 750px);
  width: 100%;
  padding: 8px 16px;
  border-radius: 12px;
  border: 1px solid var(--c--contextuals--border--surface--primary);
  background: var(--c--contextuals--background--semantic--warning--tertiary);
`;

const ACTION_BUTTON_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  padding: '2px 6px',
  fontSize: '0.75rem',
  color: 'var(--c--contextuals--content--semantic--warning--primary)',
};

export const ImageProcessingUnavailableBanner = ({
  onDismiss,
}: ImageProcessingUnavailableBannerProps) => {
  const { t } = useTranslation();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const warningColor =
    'var(--c--contextuals--content--semantic--warning--primary)';

  return (
    <Box
      data-testid="image-processing-unavailable-banner"
      role="status"
      $direction="row"
      $align="center"
      $justify="space-between"
      $gap="8px"
      $css={FLUSH_CARD_CSS}
    >
      <Box $direction="row" $align="center" $gap="8px">
        <WarningFilledIcon width={20} height={20} />
        <Text $size="sm" $color={warningColor}>
          {t('Image processing unavailable')}
        </Text>
      </Box>
      <Box $direction="row" $align="center" $gap="4px">
        <button
          type="button"
          onClick={() => setDetailsOpen(true)}
          style={ACTION_BUTTON_STYLE}
        >
          <Icon iconName="info" $size="1rem" $color={warningColor} />
          {t('More info')}
        </button>
        <button
          type="button"
          aria-label={t('Dismiss')}
          onClick={onDismiss}
          style={{ ...ACTION_BUTTON_STYLE, padding: '2px 4px' }}
        >
          <Icon iconName="close" $size="1rem" $color={warningColor} />
        </button>
      </Box>
      <Modal
        isOpen={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        title={t('Image processing unavailable')}
        closeOnClickOutside={true}
        closeOnEsc={true}
        size={ModalSize.MEDIUM}
      >
        <Text as="p" $size="sm" style={{ whiteSpace: 'pre-line' }}>
          {t(
            'Image analysis is temporarily unavailable.\nYou can continue with text requests or try again later.',
          )}
        </Text>
      </Modal>
    </Box>
  );
};
