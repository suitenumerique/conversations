import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useResponsiveStore } from '@/stores';

import { buildImpactCo2ComparateurUrl } from '../../utils/impactCo2';
import { MessageEnergyIndicator } from '../MessageEnergyIndicator';

const TEST_CO2_IMPACT_KG = 0.00002191613089507352;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { co2?: string }) =>
      opts?.co2 ? `${key}:${opts.co2}` : key,
    i18n: { resolvedLanguage: 'en' },
  }),
}));

jest.mock('@/stores', () => ({
  useResponsiveStore: jest.fn(),
}));

const mockUseResponsiveStore = jest.mocked(useResponsiveStore);

const setResponsive = (isMobile: boolean) =>
  mockUseResponsiveStore.mockReturnValue({
    isMobile,
    isDesktop: !isMobile,
    isTablet: isMobile,
    isSmallMobile: false,
    screenSize: isMobile ? 'mobile' : 'desktop',
    screenWidth: isMobile ? 600 : 1024,
    setScreenSize: jest.fn(),
    initializeResizeListener: jest.fn(() => () => {}),
  });

const renderIndicator = () =>
  render(
    <CunninghamProvider>
      <MessageEnergyIndicator co2ImpactKg={TEST_CO2_IMPACT_KG} />
    </CunninghamProvider>,
  );

describe('MessageEnergyIndicator', () => {
  beforeEach(() => {
    setResponsive(false);
  });

  it('renders the leaf button', () => {
    renderIndicator();

    expect(screen.getByTestId('message-energy-indicator')).toBeInTheDocument();
    expect(screen.getByLabelText('Carbon impact')).toBeInTheDocument();
  });

  it.each([
    ['desktop', false],
    ['mobile', true],
  ])('opens the modal with footer actions on %s click', async (_, isMobile) => {
    setResponsive(isMobile);
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByLabelText('Carbon impact'));

    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText('This request: {{co2}}:0.02 g CO₂eq'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Know more/i })).toHaveAttribute(
      'href',
      buildImpactCo2ComparateurUrl(TEST_CO2_IMPACT_KG),
    );
    expect(screen.getByRole('button', { name: 'OK' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'OK' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders the impactco2 widget container in the modal', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByLabelText('Carbon impact'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByTestId('impact-co2-widget')).toBeInTheDocument();
  });
});
