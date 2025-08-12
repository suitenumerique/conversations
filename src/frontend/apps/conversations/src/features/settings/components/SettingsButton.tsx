import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { BoxButton, Icon } from '@/components';

import { SettingsModal } from './SettingsModal';

export const SettingsButton = () => {
  const { t } = useTranslation();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <>
      <BoxButton
        aria-label={t('Settings')}
        onClick={() => setIsSettingsOpen(true)}
      >
        <Icon iconName="settings" $theme="primary" $size="24px" />
      </BoxButton>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </>
  );
};
