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

  it('renders the Figma footer and honors the app switcher flag', async () => {
    const { unmount } = render(<LeftPanelFooter />, { wrapper: AppWrapper });

    // Flag on: avatar + app switcher on the left, help on the right, and no
    // standalone settings button (settings live in the account menu).
    await screen.findByRole('button', { name: 'My Account' });
    const footer = screen.getByTestId('left-panel-footer');
    expect(
      within(footer)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['My Account', 'App switcher', 'Help']);
    expect(
      within(footer).queryByRole('button', { name: 'Settings' }),
    ).not.toBeInTheDocument();
    unmount();

    // Flag off: the app switcher disappears, the rest stays.
    mockComponentTokens = { 'la-gaufre': false };
    render(<LeftPanelFooter />, { wrapper: AppWrapper });

    expect(
      screen.queryByRole('button', { name: 'App switcher' }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'My Account' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help' })).toBeInTheDocument();
  });
});
