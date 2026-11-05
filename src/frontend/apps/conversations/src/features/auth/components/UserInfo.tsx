import { Button } from '@gouvfr-lasuite/cunningham-react';
import { UserMenu } from '@gouvfr-lasuite/ui-kit';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { LanguagePicker } from '@/features/language';
import { SettingsModal } from '@/features/settings/components/SettingsModal';

import { useAuth } from '../hooks';
import { getUserEmail, getUserFullName, gotoLogin, gotoLogout } from '../utils';

export const UserInfo = () => {
  const { t } = useTranslation();
  const { authenticated, user } = useAuth();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  if (!authenticated) {
    return (
      <Button color="brand" variant="tertiary" onClick={() => gotoLogin()}>
        {t('Login')}
      </Button>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <>
      <UserMenu
        user={{
          email: getUserEmail(user),
          full_name: getUserFullName(user, t('User')),
        }}
        // Keep the desktop-style popover on mobile instead of the fullscreen
        // modal, so the account menu stays coherent across viewports.
        withMobileView={false}
        appSettingsCTA={() => setIsSettingsOpen(true)}
        logout={gotoLogout}
        actions={<LanguagePicker />}
        termOfServiceUrl="https://docs.numerique.gouv.fr/docs/7b118d32-7f3c-4226-a3d0-92d2f33c5f0a/"
      />
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </>
  );
};
