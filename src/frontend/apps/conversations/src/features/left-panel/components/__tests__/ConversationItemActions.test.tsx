import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ConversationItemActions } from '../ConversationItemActions';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) => {
      if (options) {
        return Object.entries(options).reduce(
          (acc, [k, v]) => acc.replace(`{{${k}}}`, v),
          key,
        );
      }
      return key;
    },
  }),
}));

jest.mock('i18next', () => ({
  t: (key: string) => key,
}));

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

jest.mock('../ModalRenameConversation', () => ({
  ModalRenameConversation: ({
    onClose,
    conversation,
  }: {
    onClose: () => void;
    conversation: { id: string };
  }) => (
    <div data-testid="modal-rename-conversation">
      <span>Rename conversation {conversation.id}</span>
      <button onClick={onClose} data-testid="modal-rename-close-button">
        Close
      </button>
    </div>
  ),
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
      <button onClick={onClose} data-testid="modal-remove-close-button">
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
  it('renders the actions button', () => {
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(screen.getByTestId('dropdown-menu')).toBeInTheDocument();
    expect(
      screen.getByTestId(
        `conversation-item-actions-button-${mockConversation.id}`,
      ),
    ).toBeInTheDocument();
  });

  it('renders dropdown menu with correct aria-label', () => {
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(screen.getByTestId('dropdown-menu')).toHaveAttribute(
      'aria-label',
      'Actions list for conversation Test Conversation',
    );
  });
  it('renders dropdown menu with fallback title when conversation has no title', () => {
    const untitledConversation = { ...mockConversation, title: '' };
    render(<ConversationItemActions conversation={untitledConversation} />);

    expect(screen.getByTestId('dropdown-menu')).toHaveAttribute(
      'aria-label',
      'Actions list for conversation Untitled conversation',
    );
  });

  it('should render delete and rename options', () => {
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(
      screen.getByTestId(
        `conversation-item-actions-remove-${mockConversation.id}`,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Rename chat')).toBeInTheDocument();
    expect(screen.getByText('Delete chat')).toBeInTheDocument();
  });

  it('opens dropdown menu when clicking the actions button', async () => {
    const user = userEvent.setup();
    render(<ConversationItemActions conversation={mockConversation} />);

    const actionsButton = screen.getByLabelText(
      `Actions list for conversation ${mockConversation.title}`,
    );
    await user.click(actionsButton);

    expect(
      screen.getByTestId(
        `conversation-item-actions-rename-${mockConversation.id}`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(
        `conversation-item-actions-remove-${mockConversation.id}`,
      ),
    ).toBeInTheDocument();
  });

  it('opens delete modal when clicking delete option', async () => {
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

  it('opens rename modal when clicking rename option', async () => {
    const user = userEvent.setup();
    render(<ConversationItemActions conversation={mockConversation} />);

    expect(
      screen.queryByTestId('modal-rename-conversation'),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByTestId(
        `conversation-item-actions-rename-${mockConversation.id}`,
      ),
    );
    expect(screen.getByTestId('modal-rename-conversation')).toBeInTheDocument();
  });

  it('closes delete modal when onClose is called', async () => {
    const user = userEvent.setup();
    render(<ConversationItemActions conversation={mockConversation} />);

    await user.click(
      screen.getByTestId(
        `conversation-item-actions-remove-${mockConversation.id}`,
      ),
    );
    expect(screen.getByTestId('modal-remove-conversation')).toBeInTheDocument();

    await user.click(screen.getByTestId('modal-remove-close-button'));

    expect(
      screen.queryByTestId('modal-remove-conversation'),
    ).not.toBeInTheDocument();
  });

  it('closes rename modal when onClose is called', async () => {
    const user = userEvent.setup();
    render(<ConversationItemActions conversation={mockConversation} />);

    await user.click(
      screen.getByTestId(
        `conversation-item-actions-rename-${mockConversation.id}`,
      ),
    );

    expect(screen.getByTestId('modal-rename-conversation')).toBeInTheDocument();
    await user.click(screen.getByTestId('modal-rename-close-button'));

    expect(
      screen.queryByTestId('modal-rename-conversation'),
    ).not.toBeInTheDocument();
  });
});
