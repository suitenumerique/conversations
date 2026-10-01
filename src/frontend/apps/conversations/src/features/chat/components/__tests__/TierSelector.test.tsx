import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
  LLMConfigurationResponse,
  LLMModel,
} from '@/features/chat/api/useLLMConfiguration';

import { TierSelector } from '../TierSelector';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      key.replace(/{{(\w+)}}/g, (_, name: string) => String(options?.[name])),
  }),
}));

const llmConfig = vi.hoisted(() => ({
  data: undefined as LLMConfigurationResponse | undefined,
}));

vi.mock('@/features/chat/api/useLLMConfiguration', () => ({
  useLLMConfiguration: () => ({ data: llmConfig.data, isLoading: false }),
}));

const TIERS: NonNullable<LLMConfigurationResponse['tiers']> = [
  { slug: 'auto', label_key: 'router.tier.auto', recommended: true },
  { slug: 'simple', label_key: 'router.tier.simple', leaves: 1 },
  { slug: 'standard', label_key: 'router.tier.standard', leaves: 2 },
  { slug: 'complex', label_key: 'router.tier.complex', leaves: 3 },
];

const MODELS: LLMModel[] = [
  {
    hrid: 'model-a',
    human_readable_name: 'Model A',
    icon: '',
    is_default: true,
    model_name: 'a',
  },
];

const renderSelector = (
  props: Partial<React.ComponentProps<typeof TierSelector>> = {},
) => {
  const onTierSelect = vi.fn();
  render(
    <CunninghamProvider>
      <TierSelector
        selectedTier="auto"
        onTierSelect={onTierSelect}
        {...props}
      />
    </CunninghamProvider>,
  );
  return { onTierSelect };
};

describe('TierSelector', () => {
  beforeEach(() => {
    llmConfig.data = { models: MODELS, tiers: TIERS };
  });

  it('renders nothing when the configuration carries no tiers (router off)', () => {
    llmConfig.data = { models: MODELS };
    renderSelector();
    expect(screen.queryByTestId('tier-selector')).not.toBeInTheDocument();
  });

  it('renders nothing while the configuration is not loaded', () => {
    llmConfig.data = undefined;
    renderSelector();
    expect(screen.queryByTestId('tier-selector')).not.toBeInTheDocument();
  });

  it('offers Auto alone, the manual tiers behind one more click', async () => {
    const user = userEvent.setup();
    renderSelector();

    expect(screen.getByTestId('tier-selector-chip')).toHaveTextContent('Auto');
    expect(screen.queryByTestId('tier-selector-menu')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('tier-selector-chip'));

    const menu = screen.getByTestId('tier-selector-menu');
    expect(menu).toBeInTheDocument();
    expect(screen.getByTestId('tier-option-auto')).toHaveTextContent(
      'Recommended',
    );
    // The three manual tiers stay collapsed.
    expect(screen.getAllByRole('menuitemradio')).toHaveLength(1);
    expect(screen.queryByTestId('tier-option-simple')).not.toBeInTheDocument();
    expect(screen.getByTestId('tier-manual-toggle')).toHaveTextContent(
      'Choose the mode myself',
    );

    await user.click(screen.getByTestId('tier-manual-toggle'));

    expect(screen.getAllByRole('menuitemradio')).toHaveLength(4);
    expect(screen.getByTestId('tier-option-simple')).toHaveTextContent('Fast');
    expect(screen.getByTestId('tier-option-standard')).toHaveTextContent(
      'Balanced',
    );
    expect(screen.getByTestId('tier-option-complex')).toHaveTextContent(
      'Reasoning',
    );
    // No model name anywhere.
    expect(menu).not.toHaveTextContent('Model A');
  });

  it('grades the manual tiers by their leaves', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByTestId('tier-selector-chip'));
    await user.click(screen.getByTestId('tier-manual-toggle'));

    expect(screen.getByTestId('tier-leaves-simple')).toHaveAttribute(
      'data-leaves',
      '1',
    );
    expect(screen.getByTestId('tier-leaves-complex')).toHaveAttribute(
      'data-leaves',
      '3',
    );
    expect(screen.queryByTestId('tier-leaves-auto')).not.toBeInTheDocument();
  });

  it('opens the manual section straight away on a manual tier', async () => {
    const user = userEvent.setup();
    renderSelector({ selectedTier: 'complex' });

    await user.click(screen.getByTestId('tier-selector-chip'));

    expect(screen.getByTestId('tier-option-complex')).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('explains the hovered tier in a side tooltip', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByTestId('tier-selector-chip'));
    await user.click(screen.getByTestId('tier-manual-toggle'));

    expect(screen.getByTestId('tier-option-standard')).not.toHaveTextContent(
      'Writing, summaries, explanations',
    );
    expect(screen.queryByTestId('tier-hint')).not.toBeInTheDocument();

    await user.hover(screen.getByTestId('tier-option-standard'));

    const hint = screen.getByTestId('tier-hint');
    expect(hint).toHaveTextContent('What it is for');
    expect(hint).toHaveTextContent('Writing, summaries, explanations');

    await user.unhover(screen.getByTestId('tier-option-standard'));
    expect(screen.queryByTestId('tier-hint')).not.toBeInTheDocument();
  });

  it('emits the picked tier and closes', async () => {
    const user = userEvent.setup();
    const { onTierSelect } = renderSelector();

    await user.click(screen.getByTestId('tier-selector-chip'));
    await user.click(screen.getByTestId('tier-manual-toggle'));
    await user.click(screen.getByTestId('tier-option-complex'));

    expect(onTierSelect).toHaveBeenCalledWith('complex');
    expect(screen.queryByTestId('tier-selector-menu')).not.toBeInTheDocument();
  });

  it('shows the selected tier label on the chip', () => {
    renderSelector({ selectedTier: 'standard' });
    expect(screen.getByTestId('tier-selector-chip')).toHaveTextContent(
      'Balanced',
    );
  });
});
