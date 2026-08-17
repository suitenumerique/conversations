import { JSX, PropsWithChildren, ReactNode } from 'react';

type AnalyticEventClick = {
  eventName: 'click';
};
type AnalyticEventUser = {
  eventName: 'user';
  id: string;
  email: string;
  sub?: string;
};

/**
 * Product events forwarded as-is to the analytics backends. Listed here so
 * every captured name is discoverable from a single place, and so a typo in a
 * call site fails the build instead of creating a stray event.
 *
 * Only purely client-side interactions belong here: anything that maps to an
 * API call is captured by the backend instead, where the outcome is known for
 * certain and no ad blocker can drop it.
 *
 * Properties must stay free of user content (no titles, file names, prompts).
 */
export type AnalyticFeatureEventName = 'carbon_footprint_opened';

export type AnalyticEventProperties = Record<
  string,
  string | number | boolean | undefined
>;

type AnalyticEventFeature = {
  eventName: AnalyticFeatureEventName;
  properties?: AnalyticEventProperties;
};

export type AnalyticEvent =
  | AnalyticEventClick
  | AnalyticEventUser
  | AnalyticEventFeature;

export abstract class AbstractAnalytic {
  public constructor() {
    Analytics.registerAnalytic(this);
  }

  public abstract Provider(children: ReactNode): JSX.Element;

  public abstract trackEvent(evt: AnalyticEvent): void;

  public abstract isFeatureFlagActivated(flagName: string): boolean;
}

export class Analytics {
  private static analytics: AbstractAnalytic[] = [];

  public static clearAnalytics(): void {
    Analytics.analytics = [];
  }

  public static registerAnalytic(analytic: AbstractAnalytic): void {
    Analytics.analytics.push(analytic);
  }

  public static trackEvent(evt: AnalyticEvent): void {
    Analytics.analytics.forEach((analytic) => analytic.trackEvent(evt));
  }

  public static providers(children: ReactNode) {
    return Analytics.analytics.reduceRight(
      (acc, analytic) => analytic.Provider(acc),
      children,
    );
  }

  /**
   * Check if a feature flag is activated
   *
   * Feature flags are activated if at least one analytic is activated
   * because we don't want to hide feature if the user does not
   * use analytics (AB testing, etc)
   */
  public static isFeatureFlagActivated(flagName: string): boolean {
    if (!Analytics.analytics.length) {
      return true;
    }

    return Analytics.analytics.some((analytic) =>
      analytic.isFeatureFlagActivated(flagName),
    );
  }
}

const AnalyticsProvider = ({ children }: PropsWithChildren) => {
  return Analytics.providers(children);
};

const isFeatureFlagActivated = (flagName: string) =>
  Analytics.isFeatureFlagActivated(flagName);

const trackEvent = (evt: AnalyticEvent) => Analytics.trackEvent(evt);

export const useAnalytics = () => {
  return {
    AnalyticsProvider,
    isFeatureFlagActivated,
    trackEvent,
  };
};
