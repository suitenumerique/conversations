import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useResponsiveStore } from '@/stores';

import SettingsIcon from '../assets/settings.svg';

import { SettingsModal } from './SettingsModal';

export const SettingsButton = () => {
  const { t } = useTranslation();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const { isDesktop } = useResponsiveStore();

  return (
    <>
      <Button
        size="medium"
        color={isDesktop ? 'neutral' : 'brand'}
        variant="tertiary"
        onClick={() => setIsSettingsOpen(true)}
        aria-label={t('Settings')}
        icon={
          <SettingsIcon
            aria-hidden
            color={
              isDesktop
                ? 'var(--c--contextuals--content--semantic--neutral--tertiary)'
                : 'var(--c--contextuals--content--semantic--brand--tertiary)'
            }
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
