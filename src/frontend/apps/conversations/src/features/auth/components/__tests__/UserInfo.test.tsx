import { fireEvent, render, screen } from '@testing-library/react';

import { User } from '@/features/auth/api/types';
import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { UserInfo } from '../UserInfo';

vi.mock('@/features/auth/hooks', () => ({
  useAuth: () => ({
    authenticated: true,
    user: {
      id: 'user-1',
      email: 'jane@test.fr',
      full_name: 'Jane',
      short_name: 'Jane',
    } as User,
  }),
}));

vi.mock('@/features/language', () => ({
  LanguagePicker: () => <button type="button">Language</button>,
}));

vi.mock('@/features/settings/components/SettingsModal', () => ({
  SettingsModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="settings-modal" /> : null,
}));

vi.mock('@gouvfr-lasuite/ui-kit', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@gouvfr-lasuite/ui-kit')>()),
  UserMenu: ({
    appSettingsCTA,
    withMobileView,
  }: {
    appSettingsCTA?: () => void;
    withMobileView?: boolean;
  }) => (
    <button
      type="button"
      onClick={appSettingsCTA}
      data-with-mobile-view={withMobileView}
    >
      My Account
    </button>
  ),
}));

describe('<UserInfo />', () => {
  it('opens the settings modal from the account menu App settings entry', () => {
    render(<UserInfo />, { wrapper: AppWrapper });

    expect(screen.queryByTestId('settings-modal')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'My Account' }));

    expect(screen.getByTestId('settings-modal')).toBeInTheDocument();
  });

  it('keeps the desktop-style popover on mobile', () => {
    render(<UserInfo />, { wrapper: AppWrapper });

    expect(screen.getByRole('button', { name: 'My Account' })).toHaveAttribute(
      'data-with-mobile-view',
      'false',
    );
  });
});
