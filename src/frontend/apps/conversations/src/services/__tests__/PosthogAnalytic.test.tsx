import posthog from 'posthog-js';
import { PropsWithChildren } from 'react';

import { PostHogAnalytic } from '../PosthogAnalytic';

vi.mock('posthog-js', () => ({
  default: {
    identify: vi.fn(),
    alias: vi.fn(),
    capture: vi.fn(),
  },
}));

vi.mock('posthog-js/react', () => ({
  PostHogProvider: ({ children }: PropsWithChildren) => children,
}));

describe('PostHogAnalytic.trackEvent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('identifies the user instead of capturing an event', () => {
    new PostHogAnalytic().trackEvent({
      eventName: 'user',
      id: 'user-id',
      email: 'user@example.com',
      sub: 'user-sub',
    });

    expect(posthog.identify).toHaveBeenCalledWith('user-id', {
      email: 'user@example.com',
    });
    expect(posthog.alias).toHaveBeenCalledWith('user-sub', 'user-id');
    expect(posthog.capture).not.toHaveBeenCalled();
  });

  it('captures a feature event with its properties', () => {
    new PostHogAnalytic().trackEvent({
      eventName: 'carbon_footprint_opened',
      properties: { co2_impact_kg: 0.0002 },
    });

    expect(posthog.capture).toHaveBeenCalledWith('carbon_footprint_opened', {
      co2_impact_kg: 0.0002,
    });
  });

  it('captures a feature event that carries no properties', () => {
    new PostHogAnalytic().trackEvent({ eventName: 'carbon_footprint_opened' });

    expect(posthog.capture).toHaveBeenCalledWith(
      'carbon_footprint_opened',
      undefined,
    );
  });

  it('ignores the payload-less legacy click event', () => {
    new PostHogAnalytic().trackEvent({ eventName: 'click' });

    expect(posthog.capture).not.toHaveBeenCalled();
    expect(posthog.identify).not.toHaveBeenCalled();
  });
});
