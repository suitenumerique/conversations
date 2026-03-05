import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import { ChatProject } from '@/features/chat/types';

import { LeftPanelProjectItem } from '../LeftPanelProjectItem';

const mockPush = jest.fn();
jest.mock('next/router', () => ({
  useRouter: () => ({ push: mockPush }),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/chat/',
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));
jest.mock('i18next', () => ({
  t: (key: string) => key,
}));

// Stub child components that pull in heavy dependencies
jest.mock(
  '@/features/left-panel/components/projects/ProjectItemActions',
  () => ({
    ProjectItemActions: () => null,
  }),
);
jest.mock('@/features/left-panel/components/ConversationItemActions', () => ({
  ConversationItemActions: () => null,
}));

const renderWithProviders = (component: React.ReactNode) =>
  render(<CunninghamProvider>{component}</CunninghamProvider>);

const makeProject = (overrides?: Partial<ChatProject>): ChatProject => ({
  id: 'proj-1',
  title: 'Design System',
  icon: 'folder',
  color: 'color_6',
  llm_instructions: '',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  conversations: [
    { id: 'conv-1', title: 'Colors discussion' },
    { id: 'conv-2', title: 'Typography' },
  ],
  ...overrides,
});

describe('LeftPanelProjectItem', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    usePendingChatStore.setState({
      projectId: null,
      input: '',
      files: null,
      hasProjectInstructions: false,
    });
  });

  it('renders project title and starts collapsed', () => {
    renderWithProviders(<LeftPanelProjectItem project={makeProject()} />);

    expect(screen.getByText('Design System')).toBeInTheDocument();
    expect(screen.queryByText('Colors discussion')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Design System' }),
    ).toHaveAttribute('aria-expanded', 'false');
  });

  it('expands on click and shows conversations', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LeftPanelProjectItem project={makeProject()} />);

    await user.click(screen.getByRole('button', { name: 'Design System' }));

    expect(screen.getByText('Colors discussion')).toBeInTheDocument();
    expect(screen.getByText('Typography')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Design System' }),
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('auto-expands when currentConversationId matches a project conversation', () => {
    renderWithProviders(
      <LeftPanelProjectItem
        project={makeProject()}
        currentConversationId="conv-1"
      />,
    );

    expect(screen.getByText('Colors discussion')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Design System' }),
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('"New conversation" button sets projectId and navigates to /chat/', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LeftPanelProjectItem project={makeProject()} />);

    await user.click(
      screen.getByRole('button', { name: 'New conversation in project' }),
    );

    expect(usePendingChatStore.getState().projectId).toBe('proj-1');
    expect(mockPush).toHaveBeenCalledWith('/chat/');
  });
});
