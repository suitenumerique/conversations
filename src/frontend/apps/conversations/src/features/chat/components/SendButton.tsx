import { Button } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Icon, Text } from '@/components';

// Composant SVG pour l'icône stop
const StopIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="12"
    height="12"
    viewBox="0 0 12 12"
    fill="none"
  >
    <path
      d="M1.33333 12C0.966667 12 0.652778 11.8694 0.391667 11.6083C0.130556 11.3472 0 11.0333 0 10.6667V1.33333C0 0.966667 0.130556 0.652778 0.391667 0.391667C0.652778 0.130556 0.966667 0 1.33333 0H10.6667C11.0333 0 11.3472 0.130556 11.6083 0.391667C11.8694 0.652778 12 0.966667 12 1.33333V10.6667C12 11.0333 11.8694 11.3472 11.6083 11.6083C11.3472 11.8694 11.0333 12 10.6667 12H1.33333Z"
      fill="#EEF1F4"
    />
  </svg>
);

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

  return (
    <>
      {!isStopMode ? (
        <Button
          size="small"
          type="submit"
          aria-label={t('Send')}
          disabled={disabled || status === 'error'}
          variant="primary"
          icon={<Icon $theme="primary-text" iconName="arrow_upward" />}
        />
      ) : (
        <Button
          size="nano"
          type="button"
          aria-label={t('Stop')}
          disabled={false}
          onClick={onClick}
          className="c__button--stop bg-semantic-neutral-primary"
          icon={<StopIcon />}
        >
          <Text $theme="neutral" $variation="on-neutral">
            {t('Stop')}
          </Text>
        </Button>
      )}
    </>
  );
};
