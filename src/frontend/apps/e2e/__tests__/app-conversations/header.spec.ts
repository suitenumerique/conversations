import { expect, test } from '@playwright/test';

import {
  clickUserMenuLogout,
  expectLoginPage,
  getLanguagePickerTrigger,
  headerUserMenuTrigger,
  keyCloakSignIn,
  overrideConfig,
  randomName,
} from './common';

test.describe('Header', () => {
  test('checks all the elements are visible', async ({ page }) => {
    await page.goto('/');

    const header = page.locator('header').first();
    await expect(header).toBeVisible();

    await expect(headerUserMenuTrigger(page)).toBeVisible();

    const langPicker = await getLanguagePickerTrigger(page);
    await expect(langPicker.locator('.c__language-picker__label')).toHaveText(
      /^EN$/i,
    );
  });

  test('checks all the elements are visible with DSFR theme', async ({
    page,
  }) => {
    await overrideConfig(page, {
      FRONTEND_THEME: 'dsfr',
    });
    await page.goto('/');

    const header = page.locator('header').first();
    await expect(header).toBeVisible();

    await expect(headerUserMenuTrigger(page)).toBeVisible();

    const langPicker = await getLanguagePickerTrigger(page);
    await expect(langPicker.locator('.c__language-picker__label')).toHaveText(
      /^EN$/i,
    );

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

  test('shows current conversation title in left panel toggle button', async ({
    page,
    browserName,
  }) => {
    await page.goto('/');

    const [prompt] = randomName('header-toggle-title', browserName, 1);
    await page
      .getByRole('textbox', { name: 'Enter your message or a' })
      .fill(prompt);
    await page.keyboard.press('Enter');

    const header = page.locator('header').first();
    await header.getByRole('button', { name: 'Close the left panel' }).click();

    const openLeftPanelButton = header.getByRole('button', {
      name: 'Open the left panel',
    });
    await expect(openLeftPanelButton).toBeVisible();
    await expect(header.getByTitle(prompt)).toBeVisible();
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

    await expect(
      header.getByRole('button', { name: 'Open the left panel' }),
    ).toBeVisible();
    await expect(
      header.getByRole('button', { name: 'New chat' }),
    ).toBeVisible();
  });
});

test.describe('Header: Log out', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  // eslint-disable-next-line playwright/expect-expect
  test('checks logout button', async ({ page, browserName }) => {
    await page.goto('/');
    await keyCloakSignIn(page, browserName);

    await clickUserMenuLogout(page);

    await expectLoginPage(page);
  });
});
