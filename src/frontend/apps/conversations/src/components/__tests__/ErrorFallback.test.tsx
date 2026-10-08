import * as Sentry from '@sentry/react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ErrorFallback } from '../ErrorFallback';

const reload = vi.fn();

const Crash = () => {
  throw new Error('Failed to fetch dynamically imported module');
};

describe('ErrorFallback', () => {
  beforeEach(() => {
    vi.stubGlobal('location', { ...window.location, reload });
    reload.mockClear();
    // React reports the caught error on the console.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('replaces a crashed tree and reloads the page on click', async () => {
    const user = userEvent.setup();
    render(
      <Sentry.ErrorBoundary fallback={<ErrorFallback />}>
        <Crash />
      </Sentry.ErrorBoundary>,
    );

    await user.click(screen.getByRole('button', { name: /Reload the page/ }));

    expect(reload).toHaveBeenCalledTimes(1);
  });
});
