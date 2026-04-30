import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import SettingsIcon from '@/assets/icons/uikit-custom/gear-rounded.svg';

import { SettingsModal } from './SettingsModal';

export const SettingsButton = () => {
  const { t } = useTranslation();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <>
      <Button
        color="neutral"
        variant="tertiary"
        size="small"
        onClick={() => setIsSettingsOpen(true)}
        aria-label={t('Settings')}
        icon={
          <SettingsIcon
            aria-hidden
            color="var(--c--contextuals--content--semantic--neutral--tertiary)"
          />
        }
        className="--docs--button-settings-panel"
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </>
  );
};
