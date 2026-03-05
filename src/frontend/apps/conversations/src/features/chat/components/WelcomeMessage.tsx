import { memo } from 'react';
import { useTranslation } from 'react-i18next';

import { WelcomeLayout } from './WelcomeLayout';

export const WelcomeMessage = memo(function WelcomeMessage() {
  const { t } = useTranslation();

  return <WelcomeLayout title={t('What is on your mind?')} />;
});
