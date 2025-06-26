import { expect, test } from '@playwright/test';

import { overrideConfig } from './common';

test.beforeEach(async ({ page }) => {
  await page.goto('/home/');
});

test.describe('Home page', () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test('checks all the elements are visible', async ({ page }) => {
    await page.goto('/home/');

    // Check header content
    const header = page.locator('header').first();
    const footer = page.locator('footer').first();
    await expect(header).toBeVisible();
    await expect(
      header.getByRole('button', { name: /Language/ }),
    ).toBeVisible();
    await expect(
      header.getByRole('img', { name: 'Assistant logo' }),
    ).toBeVisible();
    await expect(
      header.getByRole('heading', { name: 'Assistant' }),
    ).toBeVisible();

    // Check the titles
    const h2 = page.locator('h2');
    await expect(h2.getByText('Govs ❤️ Open Source.')).toBeVisible();
    await expect(
      h2.getByText('Conversation with AI, simplified.'),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Start conversation' }),
    ).toBeVisible();

    await expect(footer).toBeVisible();
  });

  test('checks all the elements are visible with dsfr theme', async ({
    page,
  }) => {
    await overrideConfig(page, {
      FRONTEND_THEME: 'dsfr',
      theme_customization: {
        footer: {
          default: {
            externalLinks: [
              {
                label: 'legifrance.gouv.fr',
                href: '#',
              },
            ],
          },
        },
      },
    });

    await page.goto('/home/');

    // Check header content
    const header = page.locator('header').first();
    const footer = page.locator('footer').first();
    await expect(header).toBeVisible();
    await expect(
      header.getByRole('button', { name: /Language/ }),
    ).toBeVisible();
    await expect(
      header.getByRole('button', { name: 'Les services de La Suite numé' }),
    ).toBeVisible();
    await expect(
      header.getByRole('img', { name: 'Gouvernement Logo' }),
    ).toBeVisible();
    await expect(
      header.getByRole('img', { name: 'Assistant logo' }),
    ).toBeVisible();
    await expect(
      header.getByRole('heading', { name: 'Assistant' }),
    ).toBeVisible();
    await expect(header.getByText('BETA')).toBeVisible();

    // Check the titles
    const h2 = page.locator('h2');
    await expect(h2.getByText('Govs ❤️ Open Source.')).toBeVisible();
    await expect(
      h2.getByText('Conversation with AI, simplified.'),
    ).toBeVisible();

    await expect(
      page.getByRole('button', { name: 'Proconnect Login' }),
    ).toHaveCount(2);

    await expect(footer).toBeVisible();
  });

  test('it checks the homepage feature flag', async ({ page }) => {
    await overrideConfig(page, {
      FRONTEND_HOMEPAGE_FEATURE_ENABLED: false,
    });

    await page.goto('/');

    // Keyclock login page
    await expect(page.getByText('conversations')).toBeVisible();
    await expect(page).toHaveURL(/http:\/\/localhost:8083\/.+/);
  });
});
