import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router';

import { ConnectorConfig } from '@/core/config/api/useConfig';
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

const mockConnectors = vi.fn();
vi.mock('@/core/config', () => ({
  useAvailableConnectors: () => mockConnectors() as ConnectorConfig[],
}));

const DATAGOUV: ConnectorConfig = {
  slug: 'datagouv',
  name: 'data.gouv.fr',
  feature_flag: 'datagouv-connector',
};
const LEGI: ConnectorConfig = {
  slug: 'legi',
  name: 'Légifrance',
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
  mockConnectors.mockReturnValue([]);
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
  it('hides the data.gouv row when the connector is not available', () => {
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

  it('shows the data.gouv row reflecting the user opt-in when available', () => {
    mockConnectors.mockReturnValue([DATAGOUV]);
    mockUser.mockReturnValue({ ...user, allowed_connectors: ['datagouv'] });
    renderModal();
    expect(screen.getByLabelText('DataGouv connector')).toBeChecked();
  });

  it('turns the connector on', async () => {
    mockConnectors.mockReturnValue([DATAGOUV]);
    renderModal();
    await userEvent.click(screen.getByLabelText('DataGouv connector'));
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      allowed_connectors: ['datagouv'],
    });
  });

  it('turns the connector back off', async () => {
    mockConnectors.mockReturnValue([DATAGOUV]);
    mockUser.mockReturnValue({ ...user, allowed_connectors: ['datagouv'] });
    renderModal();
    await userEvent.click(screen.getByLabelText('DataGouv connector'));
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      allowed_connectors: [],
    });
  });

  it('lists every available connector and keeps the others switched on', async () => {
    mockConnectors.mockReturnValue([DATAGOUV, LEGI]);
    mockUser.mockReturnValue({ ...user, allowed_connectors: ['datagouv'] });
    renderModal();
    await userEvent.click(screen.getByLabelText('Légifrance connector'));
    expect(mockUpdateUser).toHaveBeenCalledWith({
      id: 'user-1',
      allowed_connectors: ['datagouv', 'legi'],
    });
  });

  describe('a connector that authenticates each user', () => {
    const SOFIA: ConnectorConfig = {
      slug: 'sofia',
      name: 'SofIA',
      feature_flag: null,
      auth: 'user_oauth',
    };
    const assign = vi.fn();

    beforeEach(() => {
      vi.stubGlobal('location', { ...window.location, assign });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('sends the user to authorize it when switched on', async () => {
      mockConnectors.mockReturnValue([SOFIA]);
      renderModal();
      await userEvent.click(screen.getByLabelText('SofIA connector'));
      expect(assign).toHaveBeenCalledWith(
        expect.stringMatching(
          /\/api\/v1\.0\/connectors\/sofia\/oauth\/start\/$/,
        ),
      );
      expect(mockUpdateUser).not.toHaveBeenCalled();
    });

    it('switches it off like any other connector', async () => {
      mockConnectors.mockReturnValue([SOFIA]);
      mockUser.mockReturnValue({ ...user, allowed_connectors: ['sofia'] });
      renderModal();
      await userEvent.click(screen.getByLabelText('SofIA connector'));
      expect(assign).not.toHaveBeenCalled();
      expect(mockUpdateUser).toHaveBeenCalledWith({
        id: 'user-1',
        allowed_connectors: [],
      });
    });
  });
});
