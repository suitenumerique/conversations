import { Button } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Icon } from '@/components/';
import { useLeftPanelStore } from '@/features/left-panel';

export const ButtonTogglePanel = () => {
  const { t } = useTranslation();
  const { isPanelOpen, togglePanel } = useLeftPanelStore();

  return (
    <Button
      size="medium"
      onClick={() => togglePanel()}
      aria-label={t('Open the header menu')}
      color="primary-text"
      icon={<Icon $theme="primary" iconName={isPanelOpen ? 'close' : 'menu'} />}
    />
  );
};
