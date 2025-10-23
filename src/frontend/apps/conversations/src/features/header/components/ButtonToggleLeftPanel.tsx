import { Button } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import LeftPanelIcon from '@/assets/icons/left-panel-bold.svg';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

export const ButtonToggleLeftPanel = () => {
  const { t } = useTranslation();
  const { isPanelOpen, togglePanel } = useChatPreferencesStore();

  return (
    <Button
      size="medium"
      onClick={() => togglePanel()}
      aria-label={
        isPanelOpen ? t('Close the left panel') : t('Open the left panel')
      }
      color="primary-text"
      icon={<LeftPanelIcon />}
      className="--docs--button-toggle-panel"
    />
  );
};
