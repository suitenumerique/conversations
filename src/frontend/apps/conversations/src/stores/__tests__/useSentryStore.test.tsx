import * as Sentry from '@sentry/react';

import { useSentryStore } from '../useSentryStore';

vi.mock('@sentry/react', () => ({
  init: vi.fn(() => ({})),
  setTag: vi.fn(),
  breadcrumbsIntegration: vi.fn(() => 'breadcrumbs'),
  replayIntegration: vi.fn(() => 'replay'),
}));

describe('useSentryStore.setSentry', () => {
  it('keeps user prompts out of breadcrumbs and replays', () => {
    useSentryStore.getState().setSentry('https://dsn.example.com/1', 'test');

    expect(Sentry.breadcrumbsIntegration).toHaveBeenCalledWith({ dom: false });
    expect(Sentry.replayIntegration).toHaveBeenCalledWith({
      maskAllText: true,
      maskAllInputs: true,
    });
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({ integrations: ['breadcrumbs', 'replay'] }),
    );
  });
});
