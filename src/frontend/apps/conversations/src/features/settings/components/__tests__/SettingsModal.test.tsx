import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router';

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
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.mockReturnValue(user);
  mockFeatureEnabled.mockReturnValue(false);
});

// The General tab holds a StyledLink, which needs a router in context.
const Wrapper = ({ children }: PropsWithChildren) => (
  <MemoryRouter>
    <AppWrapper>{children}</AppWrapper>
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
