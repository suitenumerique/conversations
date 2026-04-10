import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { InputChat } from '../InputChat';

// Mock stores and hooks
jest.mock('@/stores', () => ({
  useResponsiveStore: () => ({
    isDesktop: true,
    isMobile: false,
  }),
}));

jest.mock('@/core', () => ({
  useConfig: () => ({
    data: {
      FEATURE_FLAGS: {
        'web-search': 'enabled',
        'document-upload': 'enabled',
      },
      chat_upload_accept: '.pdf,.txt',
    },
  }),
  FeatureFlagState: {
    ENABLED: 'enabled',
    DISABLED: 'disabled',
  },
}));

jest.mock('@/libs', () => ({
  useAnalytics: () => ({
    isFeatureFlagActivated: jest.fn(() => true),
  }),
}));

jest.mock('@/components/ToastProvider', () => ({
  useToast: () => ({
    showToast: jest.fn(),
  }),
}));

jest.mock('@/features/chat/hooks/useFileDragDrop', () => ({
  useFileDragDrop: () => ({
    isDragActive: false,
  }),
}));

jest.mock('@/features/chat/hooks/useFileUrls', () => ({
  useFileUrls: () => new Map(),
}));

// Mock child components
jest.mock('../InputChatAction', () => ({
  InputChatActions: () => <div data-testid="input-chat-actions">Actions</div>,
}));

jest.mock('../SuggestionCarousel', () => ({
  SuggestionCarousel: () => (
    <div data-testid="suggestion-carousel">Suggestions</div>
  ),
}));

jest.mock('../WelcomeMessage', () => ({
  WelcomeMessage: () => <div data-testid="welcome-message">Welcome</div>,
}));

jest.mock('../AttachmentList', () => ({
  AttachmentList: () => <div data-testid="attachment-list">Attachments</div>,
}));

jest.mock('../ScrollDown', () => ({
  ScrollDown: () => <div data-testid="scroll-down">Scroll Down</div>,
}));

jest.mock('../../assets/files.svg', () => () => (
  <svg data-testid="files-icon" />
));

const defaultProps = {
  messagesLength: 0,
  input: '',
  handleInputChange: jest.fn(),
  handleSubmit: jest.fn(),
  status: 'ready' as const,
  files: null,
  setFiles: jest.fn(),
};

describe('InputChat', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
    const handleInputChange = jest.fn();
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

  it('should disable textarea when status is error', () => {
    render(<InputChat {...defaultProps} status="error" />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeDisabled();
  });

  it('should disable textarea when status is streaming', () => {
    render(<InputChat {...defaultProps} status="streaming" />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeDisabled();
  });

  it('should disable textarea when status is submitted', () => {
    render(<InputChat {...defaultProps} status="submitted" />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByRole('textbox', { name: 'Enter your message or a question' }),
    ).toBeDisabled();
  });

  it('should not submit form when pressing Enter and status is streaming', async () => {
    const user = userEvent.setup();
    const handleSubmit = jest.fn((e) => e.preventDefault());
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
    const handleSubmit = jest.fn((e) => e.preventDefault());
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
    const handleSubmit = jest.fn((e) => e.preventDefault());
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
    const handleSubmit = jest.fn((e) => e.preventDefault());
    render(<InputChat {...defaultProps} handleSubmit={handleSubmit} />, {
      wrapper: AppWrapper,
    });

    const textarea = screen.getByRole('textbox', {
      name: 'Enter your message or a question',
    });
    await user.type(textarea, '{Shift>}{Enter}{/Shift}');

    expect(handleSubmit).not.toHaveBeenCalled();
  });
});
