import { Page, expect } from '@playwright/test';

export const CONFIG = {
  ACTIVATION_REQUIRED: false,
  CRISP_WEBSITE_ID: null,
  ENVIRONMENT: 'development',
  FEATURE_FLAGS: {
    'document-upload': 'enabled',
    'web-search': 'enabled',
  },
  FRONTEND_CSS_URL: null,
  FRONTEND_HOMEPAGE_FEATURE_ENABLED: true,
  FRONTEND_THEME: null,
  MEDIA_BASE_URL: 'http://localhost:8083',
  LANGUAGES: [
    ['en-us', 'English'],
    ['fr-fr', 'Français'],
    // ['de-de', 'Deutsch'],
    // ['nl-nl', 'Nederlands'],
    // ['es-es', 'Español'],
  ],
  LANGUAGE_CODE: 'en-us',
  POSTHOG_KEY: {},
  SENTRY_DSN: null,
  theme_customization: {},
  chat_upload_accept:
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document,' +
    'application/vnd.openxmlformats-officedocument.presentationml,' +
    'application/vnd.ms-excel,' +
    'application/excel,' +
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,' +
    'text/plain,' +
    'text/csv,' +
    'application/csv,' +
    'application/pdf,' +
    'text/html,' +
    'application/xhtml+xml,' +
    'text/markdown,' +
    'application/markdown,' +
    'application/x-markdown' +
    ',application/vnd.ms-outlook,' +
    'image/jpeg,' +
    'image/png,' +
    'image/gif,' +
    'image/webp',
} as const;

export const overrideConfig = async (
  page: Page,
  newConfig: { [K in keyof typeof CONFIG]?: unknown },
) =>
  await page.route('**/api/v1.0/config/', async (route) => {
    const request = route.request();
    if (request.method().includes('GET')) {
      await route.fulfill({
        json: {
          ...CONFIG,
          ...newConfig,
        },
      });
    } else {
      await route.continue();
    }
  });

export const keyCloakSignIn = async (
  page: Page,
  browserName: string,
  fromHome: boolean = true,
) => {
  if (fromHome) {
    await page
      .getByRole('button', { name: 'Start conversation' })
      .first()
      .click();
  }

  const login = `user-e2e-${browserName}`;
  const password = `password-e2e-${browserName}`;

  await expect(page).toHaveURL(/http:\/\/localhost:8083\/.+/);
  await expect(page.getByText('conversations')).toBeVisible();

  if (await page.getByLabel('Restart login').isVisible()) {
    await page.getByLabel('Restart login').click();
  }

  await page.getByRole('textbox', { name: 'username' }).fill(login);
  await page.getByRole('textbox', { name: 'password' }).fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click({ force: true });
};

export const randomName = (name: string, browserName: string, length: number) =>
  Array.from({ length }, (_el, index) => {
    return `${browserName}-${Math.floor(Math.random() * 10000)}-${index}-${name}`;
  });

export const expectLoginPage = async (page: Page) =>
  await expect(
    page.getByRole('heading', { name: 'Your sovereign AI assistant' }),
  ).toBeVisible();
