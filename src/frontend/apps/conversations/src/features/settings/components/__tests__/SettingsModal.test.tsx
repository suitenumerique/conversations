import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router';

import { ToastProvider } from '@/components';
import { User } from '@/features/auth/api/types';
import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { SettingsModal } from '../SettingsModal';

// The Cunningham modal is force-cast onto tab props, so render every tab flat.
vi.mock('@gouvfr-lasuite/cunningham-react', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('@gouvfr-lasuite/cunningham-react')
  >()),
  Modal: ({
    tabs,
  }: {
    tabs: { id: string; label: string; content: React.ReactNode }[];
  }) => (
    <div>
      {tabs.map((tab) => (
        <section key={tab.id} data-testid={`tab-${tab.id}`}>
          <h2>{tab.label}</h2>
          {tab.content}
        </section>
      ))}
    </div>
  ),
}));

const mockUser = vi.fn();
vi.mock('@/features/auth/api', () => ({
  useAuthQuery: () => ({ data: mockUser() as User | undefined }),
}));

const mockUpdateUser = vi.fn();
vi.mock('@/core/api/useUserUpdate', () => ({
  useUserUpdate: () => ({ mutateAsync: mockUpdateUser, isPending: false }),
}));

const mockFeatureEnabled = vi.fn();
vi.mock('@/core/config', () => ({
  useFeatureEnabled: (key: string) => mockFeatureEnabled(key) as boolean,
}));

const user: User = {
  id: 'user-1',
  email: 'jane@test.fr',
  full_name: 'Jane',
  short_name: 'Jane',
  allow_smart_web_search: true,
  allow_conversation_analytics: false,
  allow_datagouv_connector: false,
  custom_guidelines: 'Be concise.',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.mockReturnValue(user);
  mockFeatureEnabled.mockReturnValue(false);
});

// The General tab holds a StyledLink, which needs a router in context.
// ToastProvider mirrors the production tree (AppProvider) for tabs using
// useToast / useClipboard. The mocked Modal renders every tab flat, so all
// tests need it.
const Wrapper = ({ children }: PropsWithChildren) => (
  <MemoryRouter>
    <AppWrapper>
      <ToastProvider>{children}</ToastProvider>
    </AppWrapper>
  </MemoryRouter>
);

const renderModal = () =>
  render(<SettingsModal isOpen onClose={vi.fn()} />, { wrapper: Wrapper });

describe('SettingsModal connectors tab', () => {
  it('hides the data.gouv row when the feature flag is off', () => {
    renderModal();
    expect(
      screen.queryByLabelText('DataGouv connector'),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId('tab-connectors')).getByLabelText(
        'Automatic web search',
      ),
    ).toBeInTheDocument();
  });

  it('shows the data.gouv row reflecting the user opt-in when the flag is on', () => {
    mockFeatureEnabled.mockReturnValue(true);
    mockUser.mockReturnValue({ ...user, allow_datagouv_connector: true });
    renderModal();
    expect(screen.getByLabelText('DataGouv connector')).toBeChecked();
  });

  it('turns the connector on', async () => {
    mockFeatureEnabled.mockReturnValue(true);
    renderModal();
    await userEvent.click(screen.getByLabelText('DataGouv connector'));
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      allow_datagouv_connector: true,
    });
  });

  it('turns the connector back off', async () => {
    mockFeatureEnabled.mockReturnValue(true);
    mockUser.mockReturnValue({ ...user, allow_datagouv_connector: true });
    renderModal();
    await userEvent.click(screen.getByLabelText('DataGouv connector'));
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      allow_datagouv_connector: false,
    });
  });
});

describe('SettingsModal personalization tab', () => {
  const writeText = vi.fn();

  const renderPersonalizationModal = () => renderModal();

  const guidelinesField = () =>
    within(screen.getByTestId('tab-personalization')).getByLabelText(
      'Your guidelines',
    );

  beforeEach(() => {
    writeText.mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
  });

  it('displays the saved guidelines with save disabled until edited', async () => {
    renderPersonalizationModal();
    const field = guidelinesField() as HTMLTextAreaElement;
    expect(field.value).toBe('Be concise.');

    const tab = screen.getByTestId('tab-personalization');
    const saveButton = within(tab).getByRole('button', { name: 'Save' });
    expect(saveButton).toBeDisabled();
    expect(within(tab).getByText('11/2000')).toBeInTheDocument();

    await userEvent.type(field, '!');
    expect(saveButton).toBeEnabled();
    await userEvent.click(saveButton);
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      custom_guidelines: 'Be concise.!',
    });
  });

  it('shows the counter and disabled copy and delete when empty', () => {
    mockUser.mockReturnValue({ ...user, custom_guidelines: '' });
    renderPersonalizationModal();
    const field = guidelinesField() as HTMLTextAreaElement;
    expect(field.value).toBe('');

    const tab = screen.getByTestId('tab-personalization');
    expect(field.placeholder).toBe(
      'Example: prefer sharp, concise answers over long explanations.',
    );
    expect(within(tab).getByText('0/2000')).toBeInTheDocument();
    expect(within(tab).getByRole('button', { name: 'Copy' })).toBeDisabled();
    expect(within(tab).getByRole('button', { name: 'Delete' })).toBeDisabled();
  });

  it('delete clears the draft without saving', async () => {
    renderPersonalizationModal();
    const tab = screen.getByTestId('tab-personalization');
    await userEvent.click(within(tab).getByRole('button', { name: 'Delete' }));
    expect((guidelinesField() as HTMLTextAreaElement).value).toBe('');
    expect(mockUpdateUser).not.toHaveBeenCalled();
    expect(within(tab).getByRole('button', { name: 'Save' })).toBeEnabled();
  });

  it('copy sends the draft to the clipboard', async () => {
    renderPersonalizationModal();
    const tab = screen.getByTestId('tab-personalization');
    await userEvent.click(within(tab).getByRole('button', { name: 'Copy' }));
    expect(writeText).toHaveBeenCalledWith('Be concise.');
  });

  it('warns against sharing personal information', () => {
    renderPersonalizationModal();
    const tab = screen.getByTestId('tab-personalization');
    expect(
      within(tab).getByText('Do not share personal information'),
    ).toBeInTheDocument();
  });
});
