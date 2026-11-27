import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { ConnectorConfig } from '@/core/config/api/useConfig';
import '@/i18n/initI18n';

import { InputChatActions } from '../InputChatAction';

const DATAGOUV: ConnectorConfig = {
  slug: 'datagouv',
  name: 'data.gouv.fr',
  description: null,
  icon: '/assets/connectors/datagouv.svg',
  feature_flag: 'datagouv-connector',
};
const SOFIA: ConnectorConfig = {
  slug: 'sofia',
  name: 'SofIA',
  description: null,
  icon: null,
  feature_flag: null,
};

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
  connectors: [],
  forcedConnectors: [],
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
  it('should offer no connector when none is available', () => {
    render(<InputChatActions {...defaultProps} onConnectorToggle={vi.fn()} />);

    expect(
      screen.queryByRole('menuitemcheckbox', { name: 'data.gouv.fr' }),
    ).not.toBeInTheDocument();
  });

  it('should offer one option per available connector, by its name', () => {
    render(
      <InputChatActions
        {...defaultProps}
        connectors={[DATAGOUV, SOFIA]}
        onConnectorToggle={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'data.gouv.fr' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('menuitemcheckbox', { name: 'SofIA' }),
    ).toBeInTheDocument();
  });

  it('should hide the connector options without a toggle handler', () => {
    render(<InputChatActions {...defaultProps} connectors={[DATAGOUV]} />);

    expect(
      screen.queryByRole('menuitemcheckbox', { name: 'data.gouv.fr' }),
    ).not.toBeInTheDocument();
  });

  it('should toggle the connector whose option is clicked', async () => {
    const user = userEvent.setup();
    const onConnectorToggle = vi.fn();
    render(
      <InputChatActions
        {...defaultProps}
        connectors={[DATAGOUV, SOFIA]}
        onConnectorToggle={onConnectorToggle}
      />,
    );

    await user.click(screen.getByRole('menuitemcheckbox', { name: 'SofIA' }));

    expect(onConnectorToggle).toHaveBeenCalledExactlyOnceWith('sofia');
  });

  it('should check and show a chip for each forced connector only', () => {
    render(
      <InputChatActions
        {...defaultProps}
        connectors={[DATAGOUV, SOFIA]}
        forcedConnectors={['sofia']}
        onConnectorToggle={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('menuitemcheckbox', { name: 'SofIA' }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(
      screen.getByRole('menuitemcheckbox', { name: 'data.gouv.fr' }),
    ).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('button', { name: 'SofIA' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(
      screen.queryByRole('button', { name: 'data.gouv.fr' }),
    ).not.toBeInTheDocument();
  });

  it('should release a forced connector from its chip', async () => {
    const user = userEvent.setup();
    const onConnectorToggle = vi.fn();
    render(
      <InputChatActions
        {...defaultProps}
        connectors={[SOFIA]}
        forcedConnectors={['sofia']}
        onConnectorToggle={onConnectorToggle}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'SofIA' }));

    expect(onConnectorToggle).toHaveBeenCalledExactlyOnceWith('sofia');
  });

  it('should show no chip for a forced connector that is not available', () => {
    render(
      <InputChatActions
        {...defaultProps}
        connectors={[SOFIA]}
        forcedConnectors={['datagouv']}
        onConnectorToggle={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'data.gouv.fr' }),
    ).not.toBeInTheDocument();
  });

  it('should show the declared icon, or the generic one', () => {
    render(
      <InputChatActions
        {...defaultProps}
        connectors={[DATAGOUV, SOFIA]}
        forcedConnectors={['datagouv', 'sofia']}
        onConnectorToggle={vi.fn()}
      />,
    );

    // Drawn as a mask filled with the text colour, like the inline icons it
    // replaces: grey in the menu, the brand colour in the chip.
    const declared = within(
      screen.getByRole('button', { name: 'data.gouv.fr' }),
    ).getByTestId('connector-icon');
    expect(declared).toHaveStyle({ width: '16px', height: '16px' });
    expect(declared.style.getPropertyValue('background-color')).toBe(
      'currentcolor',
    );
    expect(declared.style.getPropertyValue('mask-image')).toBe(
      'url("/assets/connectors/datagouv.svg")',
    );
    expect(declared).toHaveAttribute('aria-hidden', 'true');
    expect(
      within(screen.getByRole('button', { name: 'SofIA' })).getByTestId(
        'connector-icon-generic',
      ),
    ).toBeInTheDocument();
  });

  it('should leave web search alone when a connector is forced', () => {
    render(
      <InputChatActions
        {...defaultProps}
        connectors={[DATAGOUV]}
        forcedConnectors={['datagouv']}
        onConnectorToggle={vi.fn()}
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
      screen.getByRole('button', { name: 'data.gouv.fr' }),
    ).toBeInTheDocument();
  });
});
