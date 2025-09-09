import { Button } from '@openfun/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Icon } from '@/components';

import { SettingsModal } from './SettingsModal';

export const SettingsButton = () => {
  const { t } = useTranslation();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <>
      <Button
        size="medium"
        color="primary-text"
        onClick={() => setIsSettingsOpen(true)}
        aria-label={t('Settings')}
        icon={<Icon iconName="settings" $theme="primary" $size="24px" />}
        className="--docs--button-toggle-panel"
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </>
  );
};
