import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import QuestionMarkCircleIcon from '@/assets/icons/uikit-custom/question-mark-circle.svg';

import { OnboardingWelcomeModal } from './OnboardingModal';

export const OnboardingButton = () => {
  const { t } = useTranslation();
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);

  return (
    <>
      <Button
        color="neutral"
        variant="tertiary"
        size="small"
        onClick={() => setIsOnboardingOpen(true)}
        aria-label={t('Open onboarding')}
        icon={<QuestionMarkCircleIcon aria-hidden />}
      />

      <OnboardingWelcomeModal
        isOpen={isOnboardingOpen}
        onClose={() => setIsOnboardingOpen(false)}
      />
    </>
  );
};
