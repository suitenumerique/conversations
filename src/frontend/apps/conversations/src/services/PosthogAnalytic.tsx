import posthog from 'posthog-js';
import { PostHogProvider as PHProvider } from 'posthog-js/react';
import { JSX, PropsWithChildren, ReactNode, useEffect, useRef } from 'react';
import { useLocation } from 'react-router';

import { AbstractAnalytic, AnalyticEvent } from '@/libs/';

export class PostHogAnalytic extends AbstractAnalytic {
  private conf?: PostHogConf = undefined;

  public constructor(conf?: PostHogConf) {
    super();

    this.conf = conf;
  }

  public Provider(children?: ReactNode): JSX.Element {
    return <PostHogProvider conf={this.conf}>{children}</PostHogProvider>;
  }

  public trackEvent(evt: AnalyticEvent): void {
    if (evt.eventName === 'user') {
      posthog.identify(evt.id, { email: evt.email });
      if (evt.sub) {
        posthog.alias(evt.sub, evt.id);
      }
    }
  }

  public isFeatureFlagActivated(flagName: string): boolean {
    return !(
      posthog.featureFlags.getFlags().includes(flagName) &&
      posthog.isFeatureEnabled(flagName) === false
    );
  }
}

export interface PostHogConf {
  id: string;
  host: string;
}

interface PostHogProviderProps {
  conf?: PostHogConf;
}

export function PostHogProvider({
  children,
  conf,
}: PropsWithChildren<PostHogProviderProps>) {
  const { pathname } = useLocation();
  const isInitialLocation = useRef(true);

  useEffect(() => {
    if (!conf?.id || !conf?.host || posthog.__loaded) {
      return;
    }

    posthog.init(conf.id, {
      api_host: conf.host,
      person_profiles: 'always',
      loaded: (posthog) => {
        if (import.meta.env.DEV) {
          posthog.debug();
        }
      },
      capture_pageview: false,
      capture_pageleave: true,
    });
  }, [conf?.host, conf?.id]);

  useEffect(() => {
    // Next's `routeChangeComplete` never fired for the first page load, so the
    // landing page view was not captured. Kept as-is to keep the migration
    // behaviour-neutral: remove this guard to start counting it.
    if (isInitialLocation.current) {
      isInitialLocation.current = false;
      return;
    }

    posthog?.capture('$pageview');
  }, [pathname]);

  return <PHProvider client={posthog}>{children}</PHProvider>;
}
