import { Button } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Icon } from '@/components/';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

export const ButtonTogglePanel = () => {
  const { t } = useTranslation();
  const { isPanelOpen, togglePanel } = useChatPreferencesStore();

  return (
    <Button
      size="medium"
      onClick={() => togglePanel()}
      aria-label={isPanelOpen ? t('Close the menu') : t('Open the menu')}
      color="brand"
      variant="tertiary"
      icon={<Icon $theme="default" iconName={isPanelOpen ? 'close' : 'menu'} />}
      className="mobile-no-focus"
    />
  );
};
