import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { render, screen, within } from '@testing-library/react';

import { RoutingCaption } from '../RoutingCaption';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      key.replace(/{{(\w+)}}/g, (_, name: string) => String(options?.[name])),
  }),
}));

const renderCaption = (ui: React.ReactElement) =>
  render(<CunninghamProvider>{ui}</CunninghamProvider>);

describe('RoutingCaption', () => {
  it('renders nothing without a decision when the router is not running', () => {
    renderCaption(<RoutingCaption />);
    expect(screen.queryByTestId('routing-caption')).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('routing-caption-pending'),
    ).not.toBeInTheDocument();
  });

  it('shows the shimmer line while the router runs', () => {
    renderCaption(<RoutingCaption pending />);
    expect(screen.getByTestId('routing-caption-pending')).toHaveTextContent(
      'Choosing the model…',
    );
  });

  it('describes a router decision as "Auto · <model>"', () => {
    renderCaption(
      <RoutingCaption routing={{ tier: 'complex', tier_source: 'router' }} />,
    );
    const caption = screen.getByTestId('routing-caption');
    expect(caption).toHaveTextContent('Auto · Reasoning model');
    expect(screen.getByTestId('tier-pictogram')).toHaveAttribute(
      'data-tier',
      'complex',
    );
  });

  it('shows the tier a constraint raised the turn to', () => {
    renderCaption(
      <RoutingCaption
        routing={{ tier: 'standard', tier_source: 'constraint' }}
      />,
    );
    expect(screen.getByTestId('routing-caption')).toHaveTextContent(
      'Balanced model · needed for this request',
    );
    expect(screen.getByTestId('routing-caption')).not.toHaveTextContent('Auto');
  });

  it('credits the user for a pinned tier', () => {
    renderCaption(
      <RoutingCaption routing={{ tier: 'simple', tier_source: 'user' }} />,
    );
    expect(screen.getByTestId('routing-caption')).toHaveTextContent(
      'Fast model · your choice',
    );
    expect(screen.getByTestId('routing-caption')).not.toHaveTextContent('Auto');
  });

  it('lights one bar per level in the pictogram', () => {
    renderCaption(
      <RoutingCaption routing={{ tier: 'standard', tier_source: 'router' }} />,
    );
    const pictogram = within(screen.getByTestId('tier-pictogram'));
    expect(pictogram.getAllByTestId('tier-bar-on')).toHaveLength(2);
    expect(pictogram.getAllByTestId('tier-bar-off')).toHaveLength(1);
  });
});
