import { render, waitFor } from '@testing-library/react';
import i18n from 'i18next';

import { AppWrapper } from '@/tests/utils';

import { ConfigProvider } from '../ConfigProvider';
import { useConfig } from '../api/useConfig';

jest.mock('../api/useConfig', () => ({
  ...jest.requireActual('../api/useConfig'),
  useConfig: jest.fn(),
}));

jest.mock('@/features/auth', () => ({
  ...jest.requireActual('@/features/auth'),
  useAuthQuery: jest.fn(() => ({ data: undefined })),
}));

const mockUseConfig = useConfig as jest.Mock;

const makeConfig = (overrides: Record<string, unknown> = {}) => ({
  data: {
    LANGUAGES: [
      ['en-us', 'English'],
      ['fr-fr', 'Français'],
      ['de-de', 'Deutsch'],
    ],
    LANGUAGE_CODE: 'en-us',
    ...overrides,
  },
});

describe('ConfigProvider - initial language', () => {
  beforeEach(() => {
    mockUseConfig.mockReset();
  });

  // First-time visitors have no saved preference: the UI must follow the
  // browser-detected language (resolved by i18next), not the instance's
  // LANGUAGE_CODE, which defaults to Django's "en-us".
  it('keeps the browser-detected language over the instance LANGUAGE_CODE', async () => {
    await i18n.changeLanguage('fr');
    mockUseConfig.mockReturnValue(makeConfig({ LANGUAGE_CODE: 'en-us' }));

    render(<ConfigProvider>app</ConfigProvider>, { wrapper: AppWrapper });

    await waitFor(() => expect(i18n.resolvedLanguage).toBe('fr'));
  });

  it('follows a non-French browser language over the instance default', async () => {
    await i18n.changeLanguage('de');
    const changeLanguageSpy = jest.spyOn(i18n, 'changeLanguage');
    mockUseConfig.mockReturnValue(makeConfig({ LANGUAGE_CODE: 'fr-fr' }));

    render(<ConfigProvider>app</ConfigProvider>, { wrapper: AppWrapper });

    await waitFor(() => expect(i18n.resolvedLanguage).toBe('de'));
    // The instance default must never pull the UI away from the browser.
    expect(changeLanguageSpy).not.toHaveBeenCalledWith('fr');
    changeLanguageSpy.mockRestore();
  });
});
