import type { Client } from '@sentry/core';
import * as Sentry from '@sentry/react';
import { create } from 'zustand';

import packageJson from '../../package.json';

interface SentryState {
  sentry?: Client;
  setSentry: (dsn?: string, environment?: string) => void;
}

export const useSentryStore = create<SentryState>((set, get) => ({
  sentry: undefined,
  setSentry: (dsn, environment) => {
    if (get().sentry) {
      return;
    }

    const sentry = Sentry.init({
      dsn,
      environment,
      integrations: [
        // Conversation titles start as the user's first prompt, and click
        // breadcrumbs record the clicked elements' aria-label and title.
        Sentry.breadcrumbsIntegration({ dom: false }),
        Sentry.replayIntegration({ maskAllText: true, maskAllInputs: true }),
      ],
      release: packageJson.version,
      replaysSessionSampleRate: 0.1,
      replaysOnErrorSampleRate: 1.0,
      tracesSampleRate: 0.1,
    });
    Sentry.setTag('application', 'frontend');

    set({ sentry });
  },
}));
