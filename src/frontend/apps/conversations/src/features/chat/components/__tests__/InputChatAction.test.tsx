import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';

import { InputChatActions } from '../InputChatAction';

jest.mock('../ModelSelector', () => ({
  ModelSelector: ({ onModelSelect }: { onModelSelect: () => void }) => (
    <button onClick={onModelSelect} data-testid="model-selector">
      Model Selector
    </button>
  ),
}));

jest.mock('../SendButton', () => ({
  SendButton: ({
    onClick,
    disabled,
  }: {
    onClick: () => void;
    disabled: boolean;
  }) => (
    <button onClick={onClick} disabled={disabled} data-testid="send-button">
      Send
    </button>
  ),
}));

const defaultProps = {
  fileUploadEnabled: true,
  webSearchEnabled: true,
  isUploadingFiles: false,
  isMobile: false,
  forceWebSearch: false,
  onAttachClick: jest.fn(),
  selectedModel: null,
  status: null,
  inputHasContent: true,
};

describe('InputChatActions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should render attach file button', () => {
    render(<InputChatActions {...defaultProps} />);

    expect(
      screen.getByRole('button', { name: 'Add attach file' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Attach file')).toBeInTheDocument();
  });

  it('should call onAttachClick when attach button is clicked', async () => {
    const user = userEvent.setup();
    const onAttachClick = jest.fn();
    render(
      <InputChatActions {...defaultProps} onAttachClick={onAttachClick} />,
    );

    await user.click(screen.getByRole('button', { name: 'Add attach file' }));

    expect(onAttachClick).toHaveBeenCalledTimes(1);
  });

  it('should disable attach button when fileUploadEnabled is false', () => {
    render(<InputChatActions {...defaultProps} fileUploadEnabled={false} />);

    expect(
      screen.getByRole('button', { name: 'Add attach file' }),
    ).toBeDisabled();
  });

  it('should disable attach button when isUploadingFiles is true', () => {
    render(<InputChatActions {...defaultProps} isUploadingFiles={true} />);

    expect(
      screen.getByRole('button', { name: 'Add attach file' }),
    ).toBeDisabled();
  });

  it('should not show attach text on mobile', () => {
    render(<InputChatActions {...defaultProps} isMobile={true} />);

    expect(screen.queryByText('Attach file')).not.toBeInTheDocument();
  });

  it('should render web search button when onWebSearchToggle is provided', () => {
    const onWebSearchToggle = jest.fn();
    render(
      <InputChatActions
        {...defaultProps}
        onWebSearchToggle={onWebSearchToggle}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Research on the web' }),
    ).toBeInTheDocument();
  });

  it('should not render web search button when onWebSearchToggle is undefined', () => {
    render(
      <InputChatActions {...defaultProps} onWebSearchToggle={undefined} />,
    );

    expect(
      screen.queryByRole('button', { name: 'Research on the web' }),
    ).not.toBeInTheDocument();
  });

  it('should call onWebSearchToggle when web search button is clicked', async () => {
    const user = userEvent.setup();
    const onWebSearchToggle = jest.fn();
    render(
      <InputChatActions
        {...defaultProps}
        onWebSearchToggle={onWebSearchToggle}
      />,
    );

    await user.click(
      screen.getByRole('button', { name: 'Research on the web' }),
    );

    expect(onWebSearchToggle).toHaveBeenCalledTimes(1);
  });

  it('should disable web search button when webSearchEnabled is false', () => {
    render(
      <InputChatActions
        {...defaultProps}
        webSearchEnabled={false}
        onWebSearchToggle={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Research on the web' }),
    ).toBeDisabled();
  });

  it('should render model selector when onModelSelect is provided', () => {
    const onModelSelect = jest.fn();
    render(
      <InputChatActions {...defaultProps} onModelSelect={onModelSelect} />,
    );

    expect(screen.getByTestId('model-selector')).toBeInTheDocument();
  });

  it('should not render model selector when onModelSelect is undefined', () => {
    render(<InputChatActions {...defaultProps} onModelSelect={undefined} />);

    expect(screen.queryByTestId('model-selector')).not.toBeInTheDocument();
  });

  it('should render send button', () => {
    render(<InputChatActions {...defaultProps} />);

    expect(screen.getByTestId('send-button')).toBeInTheDocument();
  });

  it('should show "Web" text on mobile when forceWebSearch is active', () => {
    render(
      <InputChatActions
        {...defaultProps}
        isMobile={true}
        forceWebSearch={true}
        onWebSearchToggle={jest.fn()}
      />,
    );

    expect(screen.getByText('Web')).toBeInTheDocument();
  });

  it('should show "Research on the web" text on desktop when forceWebSearch is active', () => {
    render(
      <InputChatActions
        {...defaultProps}
        isMobile={false}
        forceWebSearch={true}
        onWebSearchToggle={jest.fn()}
      />,
    );

    expect(screen.getByText('Research on the web')).toBeInTheDocument();
    expect(screen.queryByText('Web')).not.toBeInTheDocument();
  });
});
