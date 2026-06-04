import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import packageJson from '../../../../../package.json';
import { OnboardingButton } from '../OnboardingButton';

// Config is swapped per test through this mutable holder.
let mockConfig: Record<string, unknown> | undefined;
jest.mock('@/core/config/api/useConfig', () => ({
  useConfig: () => ({ data: mockConfig }),
}));

jest.mock('@/components', () => ({
  Icon: ({ iconName }: { iconName: string }) => (
    <span data-testid={`icon-${iconName}`} />
  ),
}));

jest.mock('@/assets/icons/uikit-custom/question-mark-circle.svg', () => {
  const Svg = () => <svg data-testid="help-icon" />;
  return Svg;
});

jest.mock('../OnboardingModal', () => ({
  OnboardingWelcomeModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="onboarding-modal" /> : null,
}));

// Render the dropdown options inline so visibility/callbacks can be asserted
// without dealing with the real popover portal.
jest.mock('@gouvfr-lasuite/ui-kit', () => ({
  DropdownMenu: ({
    options,
    children,
  }: {
    options: Array<Record<string, unknown>>;
    children: React.ReactNode;
  }) => (
    <div>
      {children}
      <ul>
        {options.map((option, index) =>
          option.type === 'separator' ? (
            <li key={`sep-${index}`} role="separator" data-testid="separator" />
          ) : (
            <li key={option.label as string}>
              <button
                type="button"
                disabled={Boolean(option.isDisabled)}
                onClick={() =>
                  (option.callback as (() => void) | undefined)?.()
                }
              >
                {option.label as string}
                {option.subText ? (
                  <span>{option.subText as string}</span>
                ) : null}
              </button>
            </li>
          ),
        )}
      </ul>
    </div>
  ),
}));

const openSpy = jest.fn();

beforeAll(() => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { href: '' },
  });
});

beforeEach(() => {
  mockConfig = {
    FRONTEND_DOCUMENTATION_URL: 'https://docs.test/',
    FRONTEND_CONTACT_EMAIL: 'help@test.com',
  };
  window.open = openSpy;
  window.location.href = '';
  jest.clearAllMocks();
});

describe('OnboardingButton', () => {
  it('renders the help trigger button', () => {
    render(<OnboardingButton />, { wrapper: AppWrapper });
    expect(
      screen.getByRole('button', { name: 'Open help menu' }),
    ).toBeInTheDocument();
  });

  it('shows all items when documentation and contact are configured', () => {
    render(<OnboardingButton />, { wrapper: AppWrapper });
    expect(screen.getByText('Documentation')).toBeInTheDocument();
    expect(screen.getByText('Onboarding')).toBeInTheDocument();
    expect(screen.getByText('Contact us')).toBeInTheDocument();
    expect(screen.getByText('Latest release')).toBeInTheDocument();
    expect(screen.getByText(packageJson.version)).toBeInTheDocument();
  });

  it('hides documentation and contact items when their config is unset', () => {
    mockConfig = {};
    render(<OnboardingButton />, { wrapper: AppWrapper });
    expect(screen.queryByText('Documentation')).not.toBeInTheDocument();
    expect(screen.queryByText('Contact us')).not.toBeInTheDocument();
    // Onboarding and Latest release are always present.
    expect(screen.getByText('Onboarding')).toBeInTheDocument();
    expect(screen.getByText('Latest release')).toBeInTheDocument();
  });

  it('opens the documentation URL in a new tab', async () => {
    render(<OnboardingButton />, { wrapper: AppWrapper });
    await userEvent.click(
      screen.getByRole('button', { name: /Documentation/ }),
    );
    expect(openSpy).toHaveBeenCalledWith(
      'https://docs.test/',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('builds a mailto link for contact and navigates the current tab', async () => {
    render(<OnboardingButton />, { wrapper: AppWrapper });
    await userEvent.click(screen.getByRole('button', { name: /Contact us/ }));
    expect(window.location.href).toBe('mailto:help@test.com');
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('opens the onboarding modal when the onboarding item is clicked', async () => {
    render(<OnboardingButton />, { wrapper: AppWrapper });
    expect(screen.queryByTestId('onboarding-modal')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Onboarding/ }));
    expect(screen.getByTestId('onboarding-modal')).toBeInTheDocument();
  });

  it('shows the current version on a disabled latest-release row', () => {
    render(<OnboardingButton />, { wrapper: AppWrapper });
    const releaseItem = screen.getByRole('button', { name: /Latest release/ });
    expect(releaseItem).toBeDisabled();
    expect(releaseItem).toHaveTextContent(packageJson.version);
  });
});
