import { UserMenu } from '@gouvfr-lasuite/ui-kit';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import i18next from 'i18next';

import '@/i18n/initI18n';

import { CunninghamLocaleProvider } from '../CunninghamLocaleProvider';

const USER = { email: 'jane@example.com', full_name: 'Jane Doe' };

const openUserMenu = async () => {
  render(
    <CunninghamLocaleProvider theme="default">
      <UserMenu user={USER} logout={() => {}} termOfServiceUrl="#" />
    </CunninghamLocaleProvider>,
  );
  await userEvent.click(screen.getByRole('button'));
};

describe('CunninghamLocaleProvider', () => {
  afterEach(async () => {
    await act(() => i18next.changeLanguage('en-us'));
  });

  it('translates the user menu in French', async () => {
    await act(() => i18next.changeLanguage('fr-fr'));

    await openUserMenu();

    expect(await screen.findByText('Déconnexion')).toBeInTheDocument();
    expect(screen.getByText("Conditions d'utilisation")).toBeInTheDocument();
  });

  it('falls back to English for a language the ui-kit does not ship', async () => {
    await act(() => i18next.changeLanguage('ru'));

    await openUserMenu();

    expect(await screen.findByText('Logout')).toBeInTheDocument();
    expect(screen.getByText('Terms of Service')).toBeInTheDocument();
  });
});
