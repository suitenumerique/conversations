import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';

import { LeftPanelConversationItem } from '../left-panel/LeftPanelConversationItem';

const mockSetPanelOpen = vi.fn();
const mockNavigate = vi.hoisted(() => vi.fn());

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => mockNavigate,
}));

const mockUseResponsiveStore = vi.hoisted(() =>
  vi.fn((selector: (state: { isDesktop: boolean }) => boolean) =>
    selector({ isDesktop: true }),
  ),
);

vi.mock('@/stores', () => ({
  useResponsiveStore: mockUseResponsiveStore,
}));

vi.mock('@/features/chat/stores/useChatPreferencesStore', () => ({
  useChatPreferencesStore: vi.fn((selector) =>
    selector({ setPanelOpen: mockSetPanelOpen }),
  ),
}));

vi.mock('@/features/left-panel/components/SimpleConversationItem', () => ({
  SimpleConversationItem: ({
    conversation,
  }: {
    conversation: { title: string };
  }) => <div data-testid="simple-conversation-item">{conversation.title}</div>,
}));

vi.mock('@/features/left-panel/components/ConversationItemActions', () => ({
  ConversationItemActions: ({
    conversation,
  }: {
    conversation: { id: string };
  }) => (
    <div data-testid={`conversation-actions-${conversation.id}`}>Actions</div>
  ),
}));

const mockConversation = {
  id: 'conv-123',
  title: 'Test Conversation',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  messages: [],
};

describe('LeftPanelConversationItem', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the conversation item with link', () => {
    render(
      <LeftPanelConversationItem
        conversation={mockConversation}
        isCurrentConversation={false}
      />,
    );

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', `/chat/${mockConversation.id}/`);
  });

  it('should render SimpleConversationItem', () => {
    render(
      <LeftPanelConversationItem
        conversation={mockConversation}
        isCurrentConversation={false}
      />,
    );

    expect(screen.getByTestId('simple-conversation-item')).toBeInTheDocument();
    expect(screen.getByText('Test Conversation')).toBeInTheDocument();
  });

  it('should render ConversationItemActions', () => {
    render(
      <LeftPanelConversationItem
        conversation={mockConversation}
        isCurrentConversation={false}
      />,
    );

    expect(
      screen.getByTestId(`conversation-actions-${mockConversation.id}`),
    ).toBeInTheDocument();
  });

  it('should not close panel on click when on desktop', async () => {
    const user = userEvent.setup();
    render(
      <LeftPanelConversationItem
        conversation={mockConversation}
        isCurrentConversation={false}
      />,
    );

    await user.click(screen.getByRole('link'));

    expect(mockSetPanelOpen).not.toHaveBeenCalled();
  });

  it('should close panel on click when on mobile', async () => {
    mockUseResponsiveStore.mockImplementation((selector) =>
      selector({ isDesktop: false }),
    );

    const user = userEvent.setup();
    render(
      <LeftPanelConversationItem
        conversation={mockConversation}
        isCurrentConversation={false}
      />,
    );

    await user.click(screen.getByRole('link'));

    expect(mockSetPanelOpen).toHaveBeenCalledWith(false);
  });
});
