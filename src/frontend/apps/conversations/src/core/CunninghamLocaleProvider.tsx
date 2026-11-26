import { CunninghamProvider } from '@gouvfr-lasuite/ui-kit';
import { ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';

import { getMatchingLocales } from '@/features/language/utils/locale';

// Locales the ui-kit ships translations for (UserMenu, LaGaufre...).
const CUNNINGHAM_LOCALES = ['en-US', 'fr-FR', 'nl-NL', 'de-DE', 'es-ES'];
const DEFAULT_CUNNINGHAM_LOCALE = 'en-US';

/**
 * Cunningham provider from the ui-kit (it bundles the ui-kit translations),
 * following the i18next language. Without `currentLocale`, ui-kit components
 * always render in English.
 */
export const CunninghamLocaleProvider = (
  props: Omit<ComponentProps<typeof CunninghamProvider>, 'currentLocale'>,
) => {
  const { i18n } = useTranslation();
  const language = i18n.resolvedLanguage || i18n.language;
  const currentLocale =
    getMatchingLocales(CUNNINGHAM_LOCALES, [language])[0] ??
    DEFAULT_CUNNINGHAM_LOCALE;

  return <CunninghamProvider {...props} currentLocale={currentLocale} />;
};
