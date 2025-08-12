import { Button } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';

interface SendButtonProps {
  status: string | null;
  disabled?: boolean;
  onClick?: () => void;
}

export const SendButton = ({
  status,
  disabled = false,
  onClick,
}: SendButtonProps) => {
  const { t } = useTranslation();
  const isStopMode = status === 'submitted' || status === 'streaming';
  console.log(status);

  return (
    <>
      {status === 'error' ? (
        <Box
          $css={`
            font-size: 14px;
            font-style: italic;
          `}
        >
          <Text $color="greyscale" $weight="500" $variation="500">
            {t('An error occurred. Please try again.')}
          </Text>
        </Box>
      ) : (
        <Button
          size="small"
          type={status === 'ready' ? 'submit' : 'button'}
          aria-label={status === 'ready' ? t('Send') : t('Stop')}
          disabled={(disabled && !isStopMode) || status === 'error'}
          color="primary"
          onClick={isStopMode && onClick ? onClick : undefined}
          icon={
            <Icon
              $variation={isStopMode ? '100' : '800'}
              $theme={isStopMode ? 'greyscale' : 'primary-text'}
              iconName={status === 'ready' ? 'arrow_upward' : 'crop_square'}
            />
          }
        >
          {isStopMode && <Text $color="white">{t('Stop')}</Text>}
        </Button>
      )}
    </>
  );
};
