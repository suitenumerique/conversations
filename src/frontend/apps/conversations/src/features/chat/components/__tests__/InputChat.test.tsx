import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { InputChat } from '../InputChat';

// Mock stores and hooks
vi.mock('@/stores', () => ({
  useResponsiveStore: () => ({
    isDesktop: true,
    isMobile: false,
  }),
}));

const mockUseConfig = vi.fn();

vi.mock('@/core', () => ({
  useConfig: () => mockUseConfig(),
  useFeatureEnabled: () => true,
}));

vi.mock('@/components/ToastProvider', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}));

vi.mock('@/features/chat/hooks/useFileDragDrop', () => ({
  useFileDragDrop: () => ({
    isDragActive: false,
  }),
}));

vi.mock('@/features/chat/hooks/useFileUrls', () => ({
  useFileUrls: () => new Map(),
}));

// Mock child components
vi.mock('../InputChatAction', () => ({
  InputChatActions: () => <div data-testid="input-chat-actions">Actions</div>,
}));

vi.mock('../SuggestionCarousel', () => ({
  SuggestionCarousel: ({
    blocked,
    banners,
  }: {
    blocked?: boolean;
    banners?: Array<{ title: string; content: string; level: string }>;
  }) =>
    blocked && banners?.length ? (
      <div data-testid="suggestion-carousel">
        {banners.map((b) => b.title).join(' ')}
      </div>
    ) : (
      <div data-testid="suggestion-carousel">Suggestions</div>
    ),
}));

vi.mock('../WelcomeMessage', () => ({
  WelcomeMessage: () => <div data-testid="welcome-message">Welcome</div>,
}));

vi.mock('../AttachmentList', () => ({
  AttachmentList: () => <div data-testid="attachment-list">Attachments</div>,
}));

vi.mock('../ScrollDown', () => ({
  ScrollDown: () => <div data-testid="scroll-down">Scroll Down</div>,
}));

vi.mock('../../assets/files.svg', () => ({
  default: () => <svg data-testid="files-icon" />,
}));

const mockUseAssistantHealth = vi.fn();

vi.mock('@/features/chat/api/useAssistantHealth', () => ({
  useAssistantHealth: () => mockUseAssistantHealth(),
}));

const defaultProps = {
  messagesLength: 0,
  input: '',
  handleInputChange: vi.fn(),
  handleSubmit: vi.fn(),
  status: 'ready' as const,
  files: null,
  setFiles: vi.fn(),
};

describe('InputChat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAssistantHealth.mockReturnValue({
      data: {
        banners: [],
        blocked: false,
      },
    });
    mockUseConfig.mockReturnValue({
      data: {
        FEATURE_FLAGS: {
          'web-search': 'enabled',
          'document-upload': 'enabled',
        },
        chat_upload_accept: '.pdf,.txt,image/*',
      },
    });
  });

  it('should render the textarea', () => {
    render(<InputChat {...defaultProps} />, { wrapper: AppWrapper });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeInTheDocument();
  });

  it('should render welcome message when messagesLength is 0', () => {
    render(<InputChat {...defaultProps} messagesLength={0} />, {
      wrapper: AppWrapper,
    });

    expect(screen.getByTestId('welcome-message')).toBeInTheDocument();
  });

  it('should not render welcome message when messagesLength > 0', () => {
    render(<InputChat {...defaultProps} messagesLength={1} />, {
      wrapper: AppWrapper,
    });

    expect(screen.queryByTestId('welcome-message')).not.toBeInTheDocument();
  });

  it('should render suggestion carousel when input is empty', () => {
    render(<InputChat {...defaultProps} input="" />, { wrapper: AppWrapper });

    expect(screen.getByTestId('suggestion-carousel')).toBeInTheDocument();
  });

  it('should not render suggestion carousel when input has content', () => {
    render(<InputChat {...defaultProps} input="Hello" />, {
      wrapper: AppWrapper,
    });

    expect(screen.queryByTestId('suggestion-carousel')).not.toBeInTheDocument();
  });

  it('should render input chat actions', () => {
    render(<InputChat {...defaultProps} />, { wrapper: AppWrapper });

    expect(screen.getByTestId('input-chat-actions')).toBeInTheDocument();
  });

  it('should call handleInputChange when typing', async () => {
    const user = userEvent.setup();
    const handleInputChange = vi.fn();
    render(
      <InputChat {...defaultProps} handleInputChange={handleInputChange} />,
      { wrapper: AppWrapper },
    );

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, 'Hello');

    expect(handleInputChange).toHaveBeenCalled();
  });

  it('should keep textarea enabled when status is error', () => {
    render(<InputChat {...defaultProps} status="error" />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeEnabled();
  });

  it('should keep textarea enabled when status is streaming', () => {
    render(<InputChat {...defaultProps} status="streaming" />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeEnabled();
  });

  it('should keep textarea enabled when status is submitted', () => {
    render(<InputChat {...defaultProps} status="submitted" />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeEnabled();
  });

  it('should not submit form when pressing Enter and status is streaming', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn((e) => e.preventDefault());
    render(
      <InputChat
        {...defaultProps}
        status="streaming"
        handleSubmit={handleSubmit}
      />,
      { wrapper: AppWrapper },
    );

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, '{Enter}');

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('should not submit form when pressing Enter and status is submitted', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn((e) => e.preventDefault());
    render(
      <InputChat
        {...defaultProps}
        status="submitted"
        handleSubmit={handleSubmit}
      />,
      { wrapper: AppWrapper },
    );

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, '{Enter}');

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('should disable textarea when isUploadingFiles is true', () => {
    render(<InputChat {...defaultProps} isUploadingFiles={true} />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeDisabled();
  });

  it('should submit form when pressing Enter', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn((e) => e.preventDefault());
    render(<InputChat {...defaultProps} handleSubmit={handleSubmit} />, {
      wrapper: AppWrapper,
    });

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, '{Enter}');

    expect(handleSubmit).toHaveBeenCalled();
  });

  it('should not submit form when pressing Shift+Enter', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn((e) => e.preventDefault());
    render(<InputChat {...defaultProps} handleSubmit={handleSubmit} />, {
      wrapper: AppWrapper,
    });

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, '{Shift>}{Enter}{/Shift}');

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('should show a notice but keep the textarea typeable during an active cooldown', () => {
    render(<InputChat {...defaultProps} cooldownUntil={Date.now() + 5000} />, {
      wrapper: AppWrapper,
    });

    // The user can still draft a message during the cooldown; only sending is blocked.
    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeEnabled();
    expect(screen.getByText(/under heavy load/i)).toBeInTheDocument();
  });

  it('should keep textarea enabled when the cooldown is already past', () => {
    render(<InputChat {...defaultProps} cooldownUntil={Date.now() - 1000} />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeEnabled();
    expect(screen.queryByText(/under heavy load/i)).not.toBeInTheDocument();
  });

  it('should not submit form when pressing Enter during an active cooldown', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn((e) => e.preventDefault());
    render(
      <InputChat
        {...defaultProps}
        cooldownUntil={Date.now() + 5000}
        handleSubmit={handleSubmit}
      />,
      { wrapper: AppWrapper },
    );

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, '{Enter}');

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('should submit form when pressing Enter once the cooldown is past', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn((e) => e.preventDefault());
    render(
      <InputChat
        {...defaultProps}
        cooldownUntil={Date.now() - 1000}
        handleSubmit={handleSubmit}
      />,
      { wrapper: AppWrapper },
    );

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, '{Enter}');

    expect(handleSubmit).toHaveBeenCalled();
  });

  it('should disable textarea when assistantHealth.blocked is true', () => {
    mockUseAssistantHealth.mockReturnValue({
      data: { banners: [], blocked: true },
    });
    render(<InputChat {...defaultProps} status="ready" />, {
      wrapper: AppWrapper,
    });
    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeDisabled();
  });

  it('should keep textarea enabled when assistantHealth.blocked is false', () => {
    mockUseAssistantHealth.mockReturnValue({
      data: { banners: [], blocked: false },
    });
    render(<InputChat {...defaultProps} status="ready" />, {
      wrapper: AppWrapper,
    });
    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeEnabled();
  });

  it('should keep textarea enabled when assistantHealth data is undefined', () => {
    mockUseAssistantHealth.mockReturnValue({ data: undefined });
    render(<InputChat {...defaultProps} status="ready" />, {
      wrapper: AppWrapper,
    });
    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeEnabled();
  });

  it('should show banner title in placeholder area when blocked is true', () => {
    mockUseAssistantHealth.mockReturnValue({
      data: {
        banners: [
          { level: 'alert', title: 'Service unavailable', content: '' },
        ],
        blocked: true,
      },
    });
    render(<InputChat {...defaultProps} input="" status="ready" />, {
      wrapper: AppWrapper,
    });
    expect(screen.getByText('Service unavailable')).toBeInTheDocument();
  });

  it('uses the raw chat_upload_accept value on the file input', () => {
    render(<InputChat {...defaultProps} />, { wrapper: AppWrapper });
    const fileInput: HTMLInputElement = screen.getByTestId('chat-file-input');
    expect(fileInput.accept).toBe('.pdf,.txt,image/*');
  });
});
