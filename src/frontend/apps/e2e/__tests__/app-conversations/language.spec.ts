import { Page, expect, test } from '@playwright/test';

test.describe.serial('Language', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForLanguageSwitch(page, TestLanguage.English);
  });

  test.afterEach(async ({ page }) => {
    // Switch back to English - important for other tests to run as expected
    await waitForLanguageSwitch(page, TestLanguage.English);
  });

  test('checks language switching', async ({ page }) => {
    const header = page.locator('header').first();

    // initial language should be english
    await expect(
      page.getByRole('button', {
        name: 'New conversation',
      }),
    ).toBeVisible();

    // switch to french
    await waitForLanguageSwitch(page, TestLanguage.French);

    await expect(
      header.getByRole('button').getByText('Français'),
    ).toBeVisible();

    await expect(page.getByLabel('Se déconnecter')).toBeVisible();

    await header.getByRole('button').getByText('Français').click();
    await page.getByLabel('Deutsch').click();
    await expect(header.getByRole('button').getByText('Deutsch')).toBeVisible();

    await expect(page.getByLabel('Abmelden')).toBeVisible();
  });

  test.fixme(
    'checks that backend uses the same language as the frontend (requires translated backend)',
    async ({ page }) => {
      // Helper function to intercept and assert 404 response
      const check404Response = async (expectedDetail: string) => {
        const interceptedBackendResponse = await page.request.get(
          'http://localhost:8071/api/v1.0/chats/non-existent-uuid/',
        );

        // Assert that the intercepted error message is in the expected language
        expect(await interceptedBackendResponse.json()).toStrictEqual({
          detail: expectedDetail,
        });
      };

      // Check for English 404 response
      await check404Response('Not found.');

      await waitForLanguageSwitch(page, TestLanguage.French);

      // Check for French 404 response
      await check404Response('Pas trouvé.');
    },
  );
});

// language helper
export const TestLanguage = {
  English: {
    label: 'English',
    expectedLocale: ['en-us'],
  },
  French: {
    label: 'Français',
    expectedLocale: ['fr-fr'],
  },
  German: {
    label: 'Deutsch',
    expectedLocale: ['de-de'],
  },
} as const;

type TestLanguageKey = keyof typeof TestLanguage;
type TestLanguageValue = (typeof TestLanguage)[TestLanguageKey];

export async function waitForLanguageSwitch(
  page: Page,
  lang: TestLanguageValue,
) {
  const header = page.locator('header').first();
  const languagePicker = header.locator('.--docs--language-picker-text');
  const isAlreadyTargetLanguage = await languagePicker
    .innerText()
    .then((text) => text.toLowerCase().includes(lang.label.toLowerCase()));

  if (isAlreadyTargetLanguage) {
    return;
  }

  await languagePicker.click();
  const responsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes('/user') && resp.request().method() === 'PATCH',
  );
  await page.getByLabel(lang.label).click();
  const resolvedResponsePromise = await responsePromise;
  const responseData = await resolvedResponsePromise.json();

  expect(lang.expectedLocale).toContain(responseData.language);
}
