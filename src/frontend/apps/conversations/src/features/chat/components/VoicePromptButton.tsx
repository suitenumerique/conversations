import { Button } from '@gouvfr-lasuite/cunningham-react';
import { Mic } from '@gouvfr-lasuite/ui-kit/icons';
import { useTranslation } from 'react-i18next';

interface VoicePromptButtonProps {
  disabled?: boolean;
  onStart: () => void;
}

export const VoicePromptButton = ({
  disabled = false,
  onStart,
}: VoicePromptButtonProps) => {
  const { t } = useTranslation();

  return (
    <Button
      size="small"
      type="button"
      color="neutral"
      variant="tertiary"
      className="c__button--neutral c__button--mic"
      disabled={disabled}
      aria-label={t('Dictate your message')}
      icon={<Mic size={18} />}
      onClick={onStart}
    />
  );
};
