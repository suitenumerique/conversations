import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Fragment } from 'react';

import { AbstractAnalytic, AnalyticEvent, Analytics } from '@/libs';
import { useResponsiveStore } from '@/stores';

import { buildImpactCo2ComparateurUrl } from '../../utils/impactCo2';
import { MessageEnergyIndicator } from '../MessageEnergyIndicator';

const TEST_CO2_IMPACT_KG = 0.00002191613089507352;

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { co2?: string }) =>
      opts?.co2 ? `${key}:${opts.co2}` : key,
    i18n: { resolvedLanguage: 'en' },
  }),
}));

vi.mock('@/stores', () => ({
  useResponsiveStore: vi.fn(),
}));

const mockUseResponsiveStore = vi.mocked(useResponsiveStore);

const trackEventMock = vi.fn();

class TestAnalytic extends AbstractAnalytic {
  public Provider() {
    return <Fragment />;
  }

  public trackEvent(evt: AnalyticEvent) {
    trackEventMock(evt);
  }

  public isFeatureFlagActivated(): boolean {
    return true;
  }
}

const setResponsive = (isMobile: boolean) =>
  mockUseResponsiveStore.mockReturnValue({
    isMobile,
    isDesktop: !isMobile,
    isTablet: isMobile,
    isSmallMobile: false,
    screenSize: isMobile ? 'mobile' : 'desktop',
    screenWidth: isMobile ? 600 : 1024,
    setScreenSize: vi.fn(),
    initializeResizeListener: vi.fn(() => () => {}),
  });

const renderIndicator = () =>
  render(
    <CunninghamProvider>
      <MessageEnergyIndicator co2ImpactKg={TEST_CO2_IMPACT_KG} />
    </CunninghamProvider>,
  );

describe('MessageEnergyIndicator', () => {
  beforeEach(() => {
    trackEventMock.mockClear();
    Analytics.clearAnalytics();
    new TestAnalytic();
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
      // Decimal separator depends on the host locale (dot in CI, comma on fr)
      within(dialog).getByText(/^This request: \{\{co2\}\}:0[.,]022 g CO₂eq$/),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Know more/i })).toHaveAttribute(
      'href',
      buildImpactCo2ComparateurUrl(TEST_CO2_IMPACT_KG),
    );
    expect(screen.getByRole('button', { name: 'OK' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'OK' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('captures the carbon footprint opening, not the mere render', async () => {
    const user = userEvent.setup();
    renderIndicator();

    expect(trackEventMock).not.toHaveBeenCalled();

    await user.click(screen.getByLabelText('Carbon impact'));

    expect(trackEventMock).toHaveBeenCalledWith({
      eventName: 'carbon_footprint_opened',
      properties: { co2_impact_kg: TEST_CO2_IMPACT_KG },
    });
  });

  it('renders the impactco2 widget container in the modal', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByLabelText('Carbon impact'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByTestId('impact-co2-widget')).toBeInTheDocument();
  });
});
