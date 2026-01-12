import { expect, test } from '@playwright/test';

import { expectLoginPage, keyCloakSignIn, overrideConfig } from './common';

test.describe('Header', () => {
  test('checks all the elements are visible', async ({ page }) => {
    await page.goto('/');

    const header = page.locator('header').first();

    await expect(header.getByLabel('Assistant Logo')).toBeVisible();

    await expect(
      header.getByRole('button', {
        name: 'Logout',
      }),
    ).toBeVisible();

    await expect(header.getByText('English')).toBeVisible();
  });

  test('checks all the elements are visible with DSFR theme', async ({
    page,
  }) => {
    await overrideConfig(page, {
      FRONTEND_THEME: 'dsfr',
    });
    await page.goto('/');

    const header = page.locator('header').first();

    await expect(header.getByLabel('Assistant Logo')).toBeVisible();

    await expect(
      header.getByRole('button', {
        name: 'Logout',
      }),
    ).toBeVisible();

    await expect(header.getByText('English')).toBeVisible();

    await page.waitForTimeout(2000);

    await expect(
      header.getByRole('button', {
        name: 'Les services de LaSuite',
      }),
    ).toBeVisible();
  });

  test('checks La Gauffre interaction', async ({ page }) => {
    await overrideConfig(page, {
      FRONTEND_THEME: 'dsfr',
    });
    await page.goto('/');

    const header = page.locator('header').first();

    await page.waitForTimeout(2000);

    await expect(
      header.getByRole('button', {
        name: 'Les services de LaSuite',
      }),
    ).toBeVisible();

    /**
     * La gaufre load a js file from a remote server,
     * it takes some time to load the file and have the interaction available
     */
    // eslint-disable-next-line playwright/no-wait-for-timeout
    await page.waitForTimeout(1500);

    await header
      .getByRole('button', {
        name: 'Les services de LaSuite',
      })
      .click();

    await expect(page.getByText('Grist')).toBeVisible();
  });
});

test.describe('Header mobile', () => {
  test.use({ viewport: { width: 500, height: 1200 } });

  test('it checks the header when mobile with DSFR theme', async ({ page }) => {
    await overrideConfig(page, {
      FRONTEND_THEME: 'dsfr',
    });

    await page.goto('/');

    const header = page.locator('header').first();

    await expect(header.getByLabel('Open the menu')).toBeVisible();
    await expect(
      header.getByRole('link', { name: 'Assistant Logo' }),
    ).toBeVisible();
  });
});

test.describe('Header: Log out', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  // eslint-disable-next-line playwright/expect-expect
  test('checks logout button', async ({ page, browserName }) => {
    await page.goto('/');
    await keyCloakSignIn(page, browserName);

    await page
      .getByRole('button', {
        name: 'Logout',
      })
      .click();

    await expectLoginPage(page);
  });
});
