import { render, screen, within } from '@testing-library/react';

import { AppWrapper } from '@/tests/utils';

import { LeftPanelFooter } from '../LeftPanelFooter';

let mockComponentTokens: Record<string, unknown> = {};

vi.mock('@/cunningham', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/cunningham')>();
  return {
    ...actual,
    useCunninghamTheme: () => ({
      spacingsTokens: { sm: '8px' },
      componentTokens: mockComponentTokens,
    }),
  };
});

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

  it('renders account, app switcher and help in a shared footer', async () => {
    render(<LeftPanelFooter />, { wrapper: AppWrapper });

    expect(screen.getByTestId('left-panel-footer')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help' })).toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'App switcher' }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'My Account' }),
    ).toBeInTheDocument();
  });

  it('places account and app switcher left, help right', async () => {
    render(<LeftPanelFooter />, { wrapper: AppWrapper });

    await screen.findByRole('button', { name: 'My Account' });
    const footer = screen.getByTestId('left-panel-footer');
    const names = within(footer)
      .getAllByRole('button')
      .map((button) => button.textContent);
    expect(names).toEqual(['My Account', 'App switcher', 'Help']);
  });

  it('has no standalone settings button; settings live in the account menu', async () => {
    render(<LeftPanelFooter />, { wrapper: AppWrapper });

    await screen.findByRole('button', { name: 'My Account' });
    expect(
      within(screen.getByTestId('left-panel-footer')).queryByRole('button', {
        name: 'Settings',
      }),
    ).not.toBeInTheDocument();
  });

  it('hides the app switcher when the feature flag is off', async () => {
    mockComponentTokens = { 'la-gaufre': false };

    render(<LeftPanelFooter />, { wrapper: AppWrapper });

    expect(
      screen.queryByRole('button', { name: 'App switcher' }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'My Account' }),
    ).toBeInTheDocument();
  });
});
