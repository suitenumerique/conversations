import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';

interface ProjectImagesSkippedBannerProps {
  onDismiss: () => void;
  topOffsetPx?: number;
}

export const ProjectImagesSkippedBanner = ({
  onDismiss,
  topOffsetPx = 0,
}: ProjectImagesSkippedBannerProps) => {
  const { t } = useTranslation();

  return (
    <Box
      data-testid="project-images-skipped-banner"
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
      <Text
        $size="xs"
        $color="var(--c--contextuals--content--semantic--warning--primary)"
      >
        {t(
          "Some project images aren't being used because the current model can't read images.",
        )}
      </Text>
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
          color: 'var(--c--contextuals--content--semantic--warning--primary)',
        }}
      >
        {t('Dismiss')}
      </button>
    </Box>
  );
};
