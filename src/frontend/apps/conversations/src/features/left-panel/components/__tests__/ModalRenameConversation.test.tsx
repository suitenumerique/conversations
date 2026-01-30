import { CunninghamProvider } from '@openfun/cunningham-react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useToast } from '@/components';
import { useRenameConversation } from '@/features/chat/api/useRenameConversation';
import { ChatConversation } from '@/features/chat/types';

import { ModalRenameConversation } from '../ModalRenameConversation';

jest.mock('@/components', () => ({
  ...jest.requireActual('@/components'),
  useToast: jest.fn(),
}));

jest.mock('@/features/chat/api/useRenameConversation');

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
const renderWithProviders = (component: React.ReactNode) => {
  return render(<CunninghamProvider>{component}</CunninghamProvider>);
};

describe('ModalRenameConversation', () => {
  const mockOnClose = jest.fn();
  const mockShowToast = jest.fn();
  const mockRenameConversation = jest.fn();

  const mockConversation: ChatConversation = {
    id: 'conv-123',
    title: 'Original Title',
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  } as ChatConversation;

  beforeEach(() => {
    jest.clearAllMocks();
    (useToast as jest.Mock).mockReturnValue({
      showToast: mockShowToast,
    });
    (useRenameConversation as jest.Mock).mockReturnValue({
      mutate: mockRenameConversation,
    });
  });

  it('renders the modal with correct title and initial value', () => {
    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    expect(screen.getByText('Rename chat')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveValue('Original Title');
    expect(screen.getByText('Cancel')).toBeInTheDocument();
    expect(screen.getByText('Rename')).toBeInTheDocument();
  });

  it('updates input value when user types', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    const input = screen.getByRole('textbox');

    await user.clear(input);
    await user.type(input, 'New Title');

    expect(input).toHaveValue('New Title');
  });

  it('closes modal when Cancel button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    await user.click(screen.getByText('Cancel'));

    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('submits form with new name and shows success toast', async () => {
    const user = userEvent.setup();
    let onSuccessCallback: (() => void) | undefined;

    (useRenameConversation as jest.Mock).mockImplementation(({ onSuccess }) => {
      onSuccessCallback = onSuccess;
      return { mutate: mockRenameConversation };
    });

    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'Updated Title');
    await user.click(screen.getByText('Rename'));

    expect(mockRenameConversation).toHaveBeenCalledWith({
      conversationId: 'conv-123',
      title: 'Updated Title',
    });

    onSuccessCallback?.();

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'success',
        'The conversation has been renamed.',
        undefined,
        4000,
      );
    });
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('does not submit form when new name is empty or whitespace', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, '   ');
    await user.click(screen.getByText('Rename'));

    expect(mockRenameConversation).not.toHaveBeenCalled();
  });

  it('shows error toast when rename fails with cause', async () => {
    const user = userEvent.setup();
    let onErrorCallback: ((error: any) => void) | undefined;

    (useRenameConversation as jest.Mock).mockImplementation(({ onError }) => {
      onErrorCallback = onError;
      return { mutate: mockRenameConversation };
    });

    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'New Title');
    await user.click(screen.getByText('Rename'));

    const error = {
      cause: ['Specific error from API'],
      message: 'Generic error',
    };
    onErrorCallback?.(error);

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'Specific error from API',
        undefined,
        4000,
      );
    });
  });

  it('shows error toast with message when no cause is provided', async () => {
    const user = userEvent.setup();
    let onErrorCallback: ((error: any) => void) | undefined;

    (useRenameConversation as jest.Mock).mockImplementation(({ onError }) => {
      onErrorCallback = onError;
      return { mutate: mockRenameConversation };
    });

    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'New Title');
    await user.click(screen.getByText('Rename'));

    const error = {
      message: 'Network error',
    };
    onErrorCallback?.(error);

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'Network error',
        undefined,
        4000,
      );
    });
  });

  it('shows default error message when error has no cause or message', async () => {
    const user = userEvent.setup();
    let onErrorCallback: ((error: any) => void) | undefined;

    (useRenameConversation as jest.Mock).mockImplementation(({ onError }) => {
      onErrorCallback = onError;
      return { mutate: mockRenameConversation };
    });

    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'New Title');
    await user.click(screen.getByText('Rename'));

    const error = {};
    onErrorCallback?.(error);

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'An error occurred while renaming the conversation',
        undefined,
        4000,
      );
    });
  });

  it('enforces maxLength of 100 characters on input', () => {
    renderWithProviders(
      <ModalRenameConversation
        onClose={mockOnClose}
        conversation={mockConversation}
      />,
    );

    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('maxLength', '100');
  });
});
