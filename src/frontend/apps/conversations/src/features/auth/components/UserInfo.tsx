import { Button } from '@gouvfr-lasuite/cunningham-react';
import { UserMenu } from '@gouvfr-lasuite/ui-kit';
import { useTranslation } from 'react-i18next';

import { useConfig } from '@/core/config';
import { LanguagePicker } from '@/features/language';

import { useAuth } from '../hooks';
import { getUserEmail, getUserFullName, gotoLogin, gotoLogout } from '../utils';

export const UserInfo = () => {
  const { t } = useTranslation();
  const { authenticated, user } = useAuth();
  const { data: config } = useConfig();

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
      user={{
        email: getUserEmail(user),
        full_name: getUserFullName(user, t('User')),
      }}
      logout={gotoLogout}
      actions={<LanguagePicker />}
      termOfServiceUrl={config?.theme_customization?.terms_of_service_url}
    />
  );
};
