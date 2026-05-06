import { Page, expect, test } from '@playwright/test';

import {
  clickLanguageDropdownOption,
  getLanguagePickerTrigger,
} from './common';

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
    // initial language should be english
    await expect(
      page.getByRole('button', {
        name: 'New chat',
      }),
    ).toBeVisible();

    // switch to french
    await waitForLanguageSwitch(page, TestLanguage.French);

    const pickerAfterFrench = await getLanguagePickerTrigger(page);
    await expect(
      pickerAfterFrench.locator('.c__language-picker__label'),
    ).toHaveText(/^FR$/i);

    // Switch back to English (including backend PATCH)
    await waitForLanguageSwitch(page, TestLanguage.English);
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
  // German: {
  //   label: 'Deutsch',
  //   expectedLocale: ['de-de'],
  // },
} as const;

type TestLanguageKey = keyof typeof TestLanguage;
type TestLanguageValue = (typeof TestLanguage)[TestLanguageKey];

export async function waitForLanguageSwitch(
  page: Page,
  lang: TestLanguageValue,
) {
  const trigger = await getLanguagePickerTrigger(page);
  const label = trigger.locator('.c__language-picker__label');
  const text = (await label.innerText()).trim().toUpperCase();
  const expectedShort = lang === TestLanguage.French ? 'FR' : 'EN';

  if (text === expectedShort) {
    return;
  }

  await trigger.click();
  const responsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes('/user') && resp.request().method() === 'PATCH',
  );
  await clickLanguageDropdownOption(page, lang.label);
  const resolvedResponsePromise = await responsePromise;
  const responseData = await resolvedResponsePromise.json();

  expect(lang.expectedLocale).toContain(responseData.language);
}
