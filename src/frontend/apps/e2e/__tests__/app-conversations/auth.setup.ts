import { FullConfig, FullProject, chromium, expect } from '@playwright/test';

import { keyCloakSignIn } from './common';

const saveStorageState = async (
  browserConfig: FullProject<unknown, unknown>,
) => {
  const browserName = browserConfig?.name || 'chromium';

  const { storageState, ...useConfig } = browserConfig?.use;
  const browser = await chromium.launch();
  const context = await browser.newContext(useConfig);
  const page = await context.newPage();

  try {
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.content();
    await expect(page.getByText('Assistant').first()).toBeVisible();

    await keyCloakSignIn(page, browserName);

    await expect(
      page.locator('header').first().getByRole('button', {
        name: 'Logout',
      }),
    ).toBeVisible();

    await page.context().storageState({
      path: storageState as string,
    });
  } catch (error) {
    console.log(error);

    await page.screenshot({
      path: `./screenshots/${browserName}-${Date.now()}.png`,
    });
    // Get console logs
    const consoleLogs = await page.evaluate(() =>
      console.log(window.console.log),
    );
    console.log(consoleLogs);

    throw error;
  } finally {
    await browser.close();
  }
};

async function globalSetup(config: FullConfig) {
  /* eslint-disable @typescript-eslint/no-non-null-assertion */
  const chromeConfig = config.projects.find((p) => p.name === 'chromium')!;
  const firefoxConfig = config.projects.find((p) => p.name === 'firefox')!;
  const webkitConfig = config.projects.find((p) => p.name === 'webkit')!;
  /* eslint-enable @typescript-eslint/no-non-null-assertion */

  const results = await Promise.allSettled([
    saveStorageState(chromeConfig),
    saveStorageState(webkitConfig),
    saveStorageState(firefoxConfig),
  ]);

  const failures = results.filter(
    (r): r is PromiseRejectedResult => r.status === 'rejected',
  );

  if (failures.length > 0) {
    throw new AggregateError(
      failures.map((f) => f.reason as Error),
      `${failures.length} browser(s) failed auth setup`,
    );
  }
}

export default globalSetup;
