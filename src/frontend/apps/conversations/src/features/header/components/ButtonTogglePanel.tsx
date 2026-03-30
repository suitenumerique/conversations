import { Button } from '@gouvfr-lasuite/cunningham-react';
import { Icon } from '@gouvfr-lasuite/ui-kit';
import { useTranslation } from 'react-i18next';

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
      icon={<Icon color="default" name={isPanelOpen ? 'close' : 'menu'} />}
      className="mobile-no-focus"
    />
  );
};
