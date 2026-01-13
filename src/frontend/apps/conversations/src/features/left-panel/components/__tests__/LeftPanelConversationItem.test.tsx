import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';

import { LeftPanelConversationItem } from '../LeftPanelConversationItem';

const mockSetPanelOpen = jest.fn();
const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock('@/stores', () => ({
  useResponsiveStore: jest.fn((selector) => selector({ isDesktop: true })),
}));

jest.mock('@/features/chat/stores/useChatPreferencesStore', () => ({
  useChatPreferencesStore: jest.fn((selector) =>
    selector({ setPanelOpen: mockSetPanelOpen }),
  ),
}));

jest.mock('../SimpleConversationItem', () => ({
  SimpleConversationItem: ({
    conversation,
  }: {
    conversation: { title: string };
  }) => <div data-testid="simple-conversation-item">{conversation.title}</div>,
}));

jest.mock('../ConversationItemActions', () => ({
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
    jest.clearAllMocks();
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
    const { useResponsiveStore } = jest.requireMock('@/stores');
    useResponsiveStore.mockImplementation(
      (selector: (state: { isDesktop: boolean }) => boolean) =>
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
