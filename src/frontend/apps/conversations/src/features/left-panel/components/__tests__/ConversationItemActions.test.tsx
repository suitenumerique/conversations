import { CunninghamProvider } from '@openfun/cunningham-react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ToastProvider } from '@/components';
import { ChatConversation } from '@/features/chat/types';

import { ConversationItemActions } from '../ConversationItemActions';

const mockPush = jest.fn();
let mockPathname = '/';

jest.mock('next/router', () => ({
  useRouter: () => ({
    push: mockPush,
    pathname: mockPathname,
    route: '/',
    query: {},
    asPath: '/',
  }),
}));

jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

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

jest.mock('@/features/chat/api/useRenameConversation', () => ({
  useRenameConversation: () => ({
    mutate: jest.fn(),
  }),
}));

jest.mock('@/features/chat/api/useRemoveConversation', () => ({
  useRemoveConversation: () => ({
    mutate: jest.fn(),
  }),
}));

const renderWithProviders = (ui: React.ReactNode) => {
  return render(
    <CunninghamProvider>
      <ToastProvider>{ui}</ToastProvider>
    </CunninghamProvider>,
  );
};

describe('ConversationItemActions', () => {
  const mockConversation: ChatConversation = {
    id: 'conv-123',
    title: 'Original Title',
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  beforeEach(() => {
    jest.clearAllMocks();
    mockPathname = '/';
  });

  const renderComponent = (conversation = mockConversation) => {
    return renderWithProviders(
      <ConversationItemActions conversation={conversation} />,
    );
  };

  it('renders the actions button', () => {
    renderComponent();

    expect(
      screen.getByTestId(
        `conversation-item-actions-button-${mockConversation.id}`,
      ),
    ).toBeInTheDocument();
  });

  it('renders dropdown menu with correct aria-label', () => {
    renderComponent();

    expect(
      screen.getByLabelText(
        `Actions list for conversation ${mockConversation.title}`,
      ),
    ).toBeInTheDocument();
  });

  it('renders dropdown menu with fallback title when conversation has no title', () => {
    const untitledConversation = { ...mockConversation, title: '' };
    renderComponent(untitledConversation);

    expect(
      screen.getByLabelText(
        `Actions list for conversation Untitled conversation`,
      ),
    ).toBeInTheDocument();
  });

  it('opens dropdown menu when clicking the actions button', async () => {
    const user = userEvent.setup();
    renderComponent();

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

  it('displays rename and delete options in the dropdown', async () => {
    const user = userEvent.setup();
    renderComponent();

    const actionsButton = screen.getByLabelText(
      `Actions list for conversation ${mockConversation.title}`,
    );
    await user.click(actionsButton);

    expect(screen.getByText('Rename chat')).toBeInTheDocument();
    expect(screen.getByText('Delete chat')).toBeInTheDocument();
  });

  it('opens rename modal when clicking rename option', async () => {
    const user = userEvent.setup();
    renderComponent();

    const actionsButton = screen.getByLabelText(
      `Actions list for conversation ${mockConversation.title}`,
    );
    await user.click(actionsButton);

    const renameOption = screen.getByTestId(
      `conversation-item-actions-rename-${mockConversation.id}`,
    );
    await user.click(renameOption);
    // Modal should be open
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    expect(screen.getByRole('textbox')).toHaveValue(mockConversation.title);

    expect(screen.getByTestId('rename-chat-form')).toBeInTheDocument();
  });

  it('opens delete modal when clicking delete option', async () => {
    const user = userEvent.setup();
    renderComponent();

    const actionsButton = screen.getByLabelText(
      `Actions list for conversation ${mockConversation.title}`,
    );
    await user.click(actionsButton);

    const deleteOption = screen.getByTestId(
      `conversation-item-actions-remove-${mockConversation.id}`,
    );
    await user.click(deleteOption);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
    expect(screen.getByTestId('delete-chat-confirm')).toBeInTheDocument();
  });

  it('does not render modals initially', () => {
    renderComponent();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('delete-chat-confirm')).not.toBeInTheDocument();
    expect(screen.queryByTestId('rename-chat-form')).not.toBeInTheDocument();
  });

  it('closes rename modal when onClose is called', async () => {
    const user = userEvent.setup();
    renderComponent();

    // Open dropdown and click rename
    const actionsButton = screen.getByLabelText(
      `Actions list for conversation ${mockConversation.title}`,
    );
    await user.click(actionsButton);
    await user.click(
      screen.getByTestId(
        `conversation-item-actions-rename-${mockConversation.id}`,
      ),
    );

    // Modal should be open
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    // Close the modal
    await user.click(screen.getByText('Cancel'));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('closes delete modal when onClose is called', async () => {
    const user = userEvent.setup();
    renderComponent();

    // Open dropdown and click delete
    const actionsButton = screen.getByLabelText(
      `Actions list for conversation ${mockConversation.title}`,
    );
    await user.click(actionsButton);
    await user.click(
      screen.getByTestId(
        `conversation-item-actions-remove-${mockConversation.id}`,
      ),
    );

    // Modal should be open
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    // Close the modal
    await user.click(screen.getByText('Cancel'));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});
