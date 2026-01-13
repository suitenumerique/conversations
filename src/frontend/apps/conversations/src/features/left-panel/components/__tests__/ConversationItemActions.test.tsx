import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';

import { ConversationItemActions } from '../ConversationItemActions';

jest.mock('@/components', () => ({
  DropdownMenu: ({
    children,
    options,
    label,
  }: {
    children: React.ReactNode;
    options: { label: string; callback: () => void; testId: string }[];
    label: string;
  }) => (
    <div data-testid="dropdown-menu" aria-label={label}>
      {children}
      <ul>
        {options.map((option) => (
          <li key={option.testId}>
            <button onClick={option.callback} data-testid={option.testId}>
              {option.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  ),
  Icon: ({
    iconName,

    ...props
  }: {
    iconName: string;
  }) => <span data-icon={iconName} {...props} />,
}));

jest.mock('../ModalRemoveConversation', () => ({
  ModalRemoveConversation: ({
    onClose,
    conversation,
  }: {
    onClose: () => void;
    conversation: { id: string };
  }) => (
    <div data-testid="modal-remove-conversation">
      <span>Remove conversation {conversation.id}</span>
      <button onClick={onClose} data-testid="modal-close-button">
        Close
      </button>
    </div>
  ),
}));

const mockConversation = {
  id: 'conv-123',
  title: 'Test Conversation',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  messages: [],
};

describe('ConversationItemActions', () => {
  it('should render dropdown menu with more_horiz icon', () => {
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(screen.getByTestId('dropdown-menu')).toBeInTheDocument();
    expect(
      screen.getByTestId(
        `conversation-item-actions-button-${mockConversation.id}`,
      ),
    ).toBeInTheDocument();
  });

  it('should have correct aria-label for dropdown', () => {
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(screen.getByTestId('dropdown-menu')).toHaveAttribute(
      'aria-label',
      'Actions list for conversation Test Conversation',
    );
  });

  it('should use "Untitled conversation" when title is empty', () => {
    render(
      <ConversationItemActions
        conversation={{ ...mockConversation, title: '' }}
      />,
    );

    expect(screen.getByTestId('dropdown-menu')).toHaveAttribute(
      'aria-label',
      'Actions list for conversation Untitled conversation',
    );
  });

  it('should render delete option', () => {
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(
      screen.getByTestId(
        `conversation-item-actions-remove-${mockConversation.id}`,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Delete chat')).toBeInTheDocument();
  });

  it('should open modal when delete option is clicked', async () => {
    const user = userEvent.setup();
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(
      screen.queryByTestId('modal-remove-conversation'),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByTestId(
        `conversation-item-actions-remove-${mockConversation.id}`,
      ),
    );

    expect(screen.getByTestId('modal-remove-conversation')).toBeInTheDocument();
  });

  it('should close modal when onClose is called', async () => {
    const user = userEvent.setup();
    render(<ConversationItemActions conversation={mockConversation} />);

    await user.click(
      screen.getByTestId(
        `conversation-item-actions-remove-${mockConversation.id}`,
      ),
    );
    expect(screen.getByTestId('modal-remove-conversation')).toBeInTheDocument();

    await user.click(screen.getByTestId('modal-close-button'));

    expect(
      screen.queryByTestId('modal-remove-conversation'),
    ).not.toBeInTheDocument();
  });
});
