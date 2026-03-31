import { Button } from '@gouvfr-lasuite/cunningham-react';
import { UserMenu } from '@gouvfr-lasuite/ui-kit';
import { useTranslation } from 'react-i18next';

import { LanguagePicker } from '@/features/language';

import { useAuth } from '../hooks';
import { gotoLogin, gotoLogout } from '../utils';

export const UserInfo = () => {
  const { t } = useTranslation();
  const { authenticated, user } = useAuth();

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
    <UserMenu
      user={{ email: user.email, full_name: user.full_name }}
      logout={gotoLogout}
      actions={<LanguagePicker />}
      termOfServiceUrl="https://docs.numerique.gouv.fr/docs/7b118d32-7f3c-4226-a3d0-92d2f33c5f0a/"
    />
  );
};
