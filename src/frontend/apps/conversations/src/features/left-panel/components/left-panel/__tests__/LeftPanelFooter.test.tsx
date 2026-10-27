import { render, screen } from '@testing-library/react';

import { AppWrapper } from '@/tests/utils';

import { LeftPanelFooter } from '../LeftPanelFooter';

let mockComponentTokens: Record<string, unknown> = {};

vi.mock('@/cunningham', () => ({
  useCunninghamTheme: () => ({
    spacingsTokens: { sm: '8px' },
    componentTokens: mockComponentTokens,
  }),
}));

vi.mock('@/features/onboarding', () => ({
  OnboardingButton: () => <button type="button">Help</button>,
}));

vi.mock('@/features/settings', () => ({
  SettingsButton: () => <button type="button">Settings</button>,
}));

vi.mock('@/features/header/components/LaGaufre', () => ({
  LaGaufre: () => <button type="button">App switcher</button>,
}));

vi.mock('@/features/auth/components/UserInfo', () => ({
  UserInfo: () => <button type="button">My Account</button>,
}));

describe('<LeftPanelFooter />', () => {
  beforeEach(() => {
    mockComponentTokens = { 'la-gaufre': true };
  });

  it('renders help, settings, app switcher and account in a shared footer', async () => {
    render(<LeftPanelFooter />, { wrapper: AppWrapper });

    expect(screen.getByTestId('left-panel-footer')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Settings' }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'App switcher' }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'My Account' }),
    ).toBeInTheDocument();
  });

  it('hides the app switcher when the feature flag is off', async () => {
    mockComponentTokens = { 'la-gaufre': false };

    render(<LeftPanelFooter />, { wrapper: AppWrapper });

    expect(screen.queryByRole('button', { name: 'App switcher' })).not
      .toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'My Account' }),
    ).toBeInTheDocument();
  });
});
