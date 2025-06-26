import { expect, test } from '@playwright/test';

import { CONFIG, overrideConfig } from './common';

test.describe('Config', () => {
  test('it checks that sentry is trying to init from config endpoint', async ({
    page,
  }) => {
    await overrideConfig(page, {
      SENTRY_DSN: 'https://sentry.io/123',
    });

    const invalidMsg = 'Invalid Sentry Dsn: https://sentry.io/123';
    const consoleMessage = page.waitForEvent('console', {
      timeout: 5000,
      predicate: (msg) => msg.text().includes(invalidMsg),
    });

    await page.goto('/');

    expect((await consoleMessage).text()).toContain(invalidMsg);
  });

  test('it checks that Crisp is trying to init from config endpoint', async ({
    page,
  }) => {
    await overrideConfig(page, {
      CRISP_WEBSITE_ID: '1234',
    });

    await page.goto('/');

    await expect(
      page.locator('#crisp-chatbox').getByText('Invalid website'),
    ).toBeVisible();
  });

  test('it checks FRONTEND_CSS_URL config', async ({ page }) => {
    await overrideConfig(page, {
      FRONTEND_CSS_URL: 'http://localhost:123465/css/style.css',
    });

    await page.goto('/');

    await expect(
      page
        .locator('head link[href="http://localhost:123465/css/style.css"]')
        .first(),
    ).toBeAttached();
  });
});

test.describe('Config: Not logged', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('it checks the config api is called', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/config/') &&
        response.status() === 200 &&
        response.request().method() === 'GET',
    );

    await page.goto('/');

    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();

    const json = (await response.json()) as typeof CONFIG;
    const { theme_customization, ...configApi } = json;
    expect(theme_customization).toBeDefined();
    const { theme_customization: _, ...CONFIG_LEFT } = CONFIG;

    expect(configApi).toStrictEqual(CONFIG_LEFT);
  });

  test('it checks that theme is configured from config endpoint', async ({
    page,
  }) => {
    await overrideConfig(page, {
      FRONTEND_THEME: 'dsfr',
    });

    await page.goto('/');

    const header = page.locator('header').first();
    // alt 'Gouvernement Logo' comes from the theme
    await expect(header.getByAltText('Gouvernement Logo')).toBeVisible();
  });
});
