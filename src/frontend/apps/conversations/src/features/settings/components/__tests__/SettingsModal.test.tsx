import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router';

import type { ConnectorConfig } from '@/core/config/api/useConfig';
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

const mockAvailableConnectors = vi.fn();
vi.mock('@/core/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/core/config')>()),
  useAvailableConnectors: () => mockAvailableConnectors() as ConnectorConfig[],
}));

const DATAGOUV: ConnectorConfig = {
  slug: 'datagouv',
  name: 'data.gouv.fr',
  description: {
    en: 'Let the Assistant search French public open data.',
    fr: 'Autoriser l’Assistant à rechercher dans les données publiques.',
  },
  icon: null,
  feature_flag: 'datagouv-connector',
};
const SOFIA: ConnectorConfig = {
  slug: 'sofia',
  name: 'SofIA',
  description: null,
  icon: null,
  feature_flag: null,
};

const user: User = {
  id: 'user-1',
  email: 'jane@test.fr',
  full_name: 'Jane',
  short_name: 'Jane',
  allow_smart_web_search: true,
  allow_conversation_analytics: false,
  allowed_connectors: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.mockReturnValue(user);
  mockAvailableConnectors.mockReturnValue([]);
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
  it('shows no connector row when none is available', () => {
    renderModal();
    expect(
      screen.queryByLabelText('data.gouv.fr connector'),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId('tab-connectors')).getByLabelText(
        'Automatic web search',
      ),
    ).toBeInTheDocument();
  });

  it('shows one row per available connector, by its name', () => {
    mockAvailableConnectors.mockReturnValue([DATAGOUV, SOFIA]);
    renderModal();
    const tab = within(screen.getByTestId('tab-connectors'));
    expect(tab.getByText('data.gouv.fr')).toBeInTheDocument();
    expect(tab.getByText('SofIA')).toBeInTheDocument();
    expect(tab.getByLabelText('SofIA connector')).toBeInTheDocument();
  });

  it('describes a connector in the user language', () => {
    mockAvailableConnectors.mockReturnValue([DATAGOUV]);
    renderModal();
    expect(
      screen.getByText('Let the Assistant search French public open data.'),
    ).toBeInTheDocument();
  });

  it('reflects each connector opt-in', () => {
    mockAvailableConnectors.mockReturnValue([DATAGOUV, SOFIA]);
    mockUser.mockReturnValue({ ...user, allowed_connectors: ['sofia'] });
    renderModal();
    expect(screen.getByLabelText('SofIA connector')).toBeChecked();
    expect(screen.getByLabelText('data.gouv.fr connector')).not.toBeChecked();
  });

  it('turns a connector on, keeping the others', async () => {
    mockAvailableConnectors.mockReturnValue([DATAGOUV, SOFIA]);
    mockUser.mockReturnValue({ ...user, allowed_connectors: ['sofia'] });
    renderModal();
    await userEvent.click(screen.getByLabelText('data.gouv.fr connector'));
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      allowed_connectors: ['sofia', 'datagouv'],
    });
  });

  it('turns a connector back off, keeping the others', async () => {
    mockAvailableConnectors.mockReturnValue([DATAGOUV, SOFIA]);
    mockUser.mockReturnValue({
      ...user,
      allowed_connectors: ['datagouv', 'gone', 'sofia'],
    });
    renderModal();
    await userEvent.click(screen.getByLabelText('data.gouv.fr connector'));
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      allowed_connectors: ['gone', 'sofia'],
    });
  });
});
