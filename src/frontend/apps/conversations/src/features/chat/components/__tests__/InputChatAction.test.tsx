import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';

import { InputChatActions } from '../InputChatAction';

vi.mock('../ModelSelector', () => ({
  ModelSelector: ({ onModelSelect }: { onModelSelect: () => void }) => (
    <button onClick={onModelSelect} data-testid="model-selector">
      Model Selector
    </button>
  ),
}));

vi.mock('../SendButton', () => ({
  SendButton: ({
    onClick,
    disabled,
    status,
  }: {
    onClick: () => void;
    disabled: boolean;
    status: string | null;
  }) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-testid="send-button"
      data-status={status ?? ''}
    >
      Send
    </button>
  ),
}));

vi.mock('@gouvfr-lasuite/ui-kit', () => ({
  DropdownMenu: ({
    options,
    children,
  }: {
    options: Array<Record<string, unknown>>;
    children: React.ReactNode;
  }) => (
    <div>
      {children}
      <ul>
        {options.map((option, index) =>
          option.type === 'separator' ? (
            <li key={`sep-${index}`} role="separator" data-testid="separator" />
          ) : (
            <li key={option.label as string}>
              <button
                type="button"
                role={
                  option.isChecked === undefined
                    ? undefined
                    : 'menuitemcheckbox'
                }
                disabled={Boolean(option.isDisabled)}
                aria-checked={
                  option.isChecked === undefined
                    ? undefined
                    : Boolean(option.isChecked)
                }
                onClick={() =>
                  (option.callback as (() => void) | undefined)?.()
                }
              >
                {option.label as string}
              </button>
            </li>
          ),
        )}
      </ul>
    </div>
  ),
}));

const defaultProps = {
  fileUploadEnabled: true,
  webSearchEnabled: true,
  isUploadingFiles: false,
  isMobile: false,
  forceWebSearch: false,
  datagouvEnabled: false,
  forceDatagouv: false,
  onAttachClick: vi.fn(),
  selectedModel: null,
  status: null,
  inputHasContent: true,
};

describe('InputChatActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the + actions menu button', () => {
    render(<InputChatActions {...defaultProps} />);

    const menuButton = screen.getByRole('button', {
      name: 'Open input actions menu',
    });
    expect(menuButton).toBeInTheDocument();
    expect(menuButton).toHaveAttribute('aria-haspopup', 'menu');
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');
  });

  it('should render attach file option in the menu', () => {
    render(<InputChatActions {...defaultProps} />);

    expect(
      screen.getByRole('button', { name: 'Attach file' }),
    ).toBeInTheDocument();
  });

  it('should call onAttachClick when attach option is clicked', async () => {
    const user = userEvent.setup();
    const onAttachClick = vi.fn();
    render(
      <InputChatActions {...defaultProps} onAttachClick={onAttachClick} />,
    );

    await user.click(screen.getByRole('button', { name: 'Attach file' }));

    expect(onAttachClick).toHaveBeenCalledTimes(1);
  });

  it('should disable attach option when fileUploadEnabled is false', () => {
    render(<InputChatActions {...defaultProps} fileUploadEnabled={false} />);

    expect(screen.getByRole('button', { name: 'Attach file' })).toBeDisabled();
  });

  it('should disable attach option when isUploadingFiles is true', () => {
    render(<InputChatActions {...defaultProps} isUploadingFiles={true} />);

    expect(screen.getByRole('button', { name: 'Attach file' })).toBeDisabled();
  });

  it('should render a separator before the web search option', () => {
    render(<InputChatActions {...defaultProps} onWebSearchToggle={vi.fn()} />);

    expect(screen.getByTestId('separator')).toBeInTheDocument();
  });

  it('should not render a separator when onWebSearchToggle is undefined', () => {
    render(
      <InputChatActions {...defaultProps} onWebSearchToggle={undefined} />,
    );

    expect(screen.queryByTestId('separator')).not.toBeInTheDocument();
  });

  it('should render web search option when onWebSearchToggle is provided', () => {
    const onWebSearchToggle = vi.fn();
    render(
      <InputChatActions
        {...defaultProps}
        onWebSearchToggle={onWebSearchToggle}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Research on the web' }),
    ).toBeInTheDocument();
  });

  it('should not render web search option when onWebSearchToggle is undefined', () => {
    render(
      <InputChatActions {...defaultProps} onWebSearchToggle={undefined} />,
    );

    expect(
      screen.queryByRole('menuitemcheckbox', { name: 'Research on the web' }),
    ).not.toBeInTheDocument();
  });

  it('should call onWebSearchToggle when web search option is clicked', async () => {
    const user = userEvent.setup();
    const onWebSearchToggle = vi.fn();
    render(
      <InputChatActions
        {...defaultProps}
        onWebSearchToggle={onWebSearchToggle}
      />,
    );

    await user.click(
      screen.getByRole('menuitemcheckbox', { name: 'Research on the web' }),
    );

    expect(onWebSearchToggle).toHaveBeenCalledTimes(1);
  });

  it('should disable web search option when webSearchEnabled is false', () => {
    render(
      <InputChatActions
        {...defaultProps}
        webSearchEnabled={false}
        onWebSearchToggle={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Research on the web' }),
    ).toBeDisabled();
  });

  it('should mark menu option as checked and show chip when forceWebSearch is active', () => {
    render(
      <InputChatActions
        {...defaultProps}
        forceWebSearch={true}
        onWebSearchToggle={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Research on the web' }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(
      screen.getByRole('button', { name: 'Research on the web' }),
    ).toHaveAttribute('aria-pressed', 'true');
  });

  it('should show "Web" chip text on mobile when forceWebSearch is active', () => {
    render(
      <InputChatActions
        {...defaultProps}
        isMobile={true}
        forceWebSearch={true}
        onWebSearchToggle={vi.fn()}
      />,
    );

    expect(screen.getByText('Web')).toBeInTheDocument();
  });

  it('should call onWebSearchToggle when chip is clicked', async () => {
    const user = userEvent.setup();
    const onWebSearchToggle = vi.fn();
    render(
      <InputChatActions
        {...defaultProps}
        forceWebSearch={true}
        onWebSearchToggle={onWebSearchToggle}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Research on the web' }),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: 'Research on the web' }),
    );

    expect(onWebSearchToggle).toHaveBeenCalledTimes(1);
  });

  it('should render model selector when onModelSelect is provided', () => {
    const onModelSelect = vi.fn();
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

  it('should pass streaming status to SendButton', () => {
    render(<InputChatActions {...defaultProps} status="streaming" />);

    expect(screen.getByTestId('send-button')).toHaveAttribute(
      'data-status',
      'streaming',
    );
  });

  it('should pass submitted status to SendButton', () => {
    render(<InputChatActions {...defaultProps} status="submitted" />);

    expect(screen.getByTestId('send-button')).toHaveAttribute(
      'data-status',
      'submitted',
    );
  });
  it('should not render the DataGouv option outside the cohort', () => {
    render(
      <InputChatActions
        {...defaultProps}
        datagouvEnabled={false}
        onDatagouvToggle={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole('menuitemcheckbox', { name: 'DataGouv' }),
    ).not.toBeInTheDocument();
  });

  it('should render the DataGouv option inside the cohort', () => {
    render(
      <InputChatActions
        {...defaultProps}
        datagouvEnabled={true}
        onDatagouvToggle={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'DataGouv' }),
    ).toBeInTheDocument();
  });

  it('should call onDatagouvToggle when the DataGouv option is clicked', async () => {
    const user = userEvent.setup();
    const onDatagouvToggle = vi.fn();
    render(
      <InputChatActions
        {...defaultProps}
        datagouvEnabled={true}
        onDatagouvToggle={onDatagouvToggle}
      />,
    );

    await user.click(
      screen.getByRole('menuitemcheckbox', { name: 'DataGouv' }),
    );

    expect(onDatagouvToggle).toHaveBeenCalledTimes(1);
  });

  it('should mark the option as checked and show a chip when forceDatagouv is active', () => {
    render(
      <InputChatActions
        {...defaultProps}
        datagouvEnabled={true}
        forceDatagouv={true}
        onDatagouvToggle={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'DataGouv' }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('button', { name: 'DataGouv' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('should show "Data" chip text on mobile when forceDatagouv is active', () => {
    render(
      <InputChatActions
        {...defaultProps}
        isMobile={true}
        datagouvEnabled={true}
        forceDatagouv={true}
        onDatagouvToggle={vi.fn()}
      />,
    );

    expect(screen.getByText('Data')).toBeInTheDocument();
  });

  it('should leave web search alone when DataGouv is forced', () => {
    render(
      <InputChatActions
        {...defaultProps}
        datagouvEnabled={true}
        forceDatagouv={true}
        onDatagouvToggle={vi.fn()}
        onWebSearchToggle={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Research on the web' }),
    ).toHaveAttribute('aria-checked', 'false');
    expect(
      screen.queryByRole('button', { name: 'Research on the web' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'DataGouv' }),
    ).toBeInTheDocument();
  });

  // The mobile chip reads "Data" to fit; the connector is still named in full
  // to anyone not reading the screen.
  it('should keep the mobile chip reachable by its full name', () => {
    render(
      <InputChatActions
        {...defaultProps}
        isMobile={true}
        datagouvEnabled={true}
        forceDatagouv={true}
        onDatagouvToggle={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'DataGouv' })).toHaveTextContent(
      'Data',
    );
  });
});
