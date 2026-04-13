import { LanguagePicker as LanguagePickerUi } from '@gouvfr-lasuite/ui-kit';
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useConfig } from '@/core';
import { useAuth } from '@/features/auth/hooks';

import { useSynchronizedLanguage } from '../hooks/useSynchronizedLanguage';

export type LanguagePickerTriggerColor = 'brand' | 'neutral';

export type LanguagePickerProps = {
  color?: LanguagePickerTriggerColor;
  size?: 'small' | 'medium' | 'nano';
  compact?: boolean;
};

const ENABLED_LANGUAGE_ISO_CODES = new Set(['fr', 'en']);
const toIsoCode = (locale: string) => locale.split(/[-_]/)[0].toLowerCase();
const toUiLocale = (locale: string) => {
  const [lang, region] = locale.split(/[-_]/);
  const normalizedLang = (lang || 'en').toLowerCase();
  const normalizedRegion = (region || normalizedLang).toUpperCase();
  return `${normalizedLang}-${normalizedRegion}`;
};

export const LanguagePicker = ({
  color,
  size = 'small',
  compact = true,
}: LanguagePickerProps = {}) => {
  const { i18n } = useTranslation();
  const { data: config } = useConfig();
  const { user } = useAuth();
  const { changeLanguageSynchronized } = useSynchronizedLanguage();

  const availableLanguages = useMemo(() => {
    const fromConfig = config?.LANGUAGES?.map(([locale]) => locale) ?? [];
    const source =
      fromConfig.length > 0
        ? fromConfig
        : Object.keys(i18n?.options?.resources || { en: true });

    const filtered = source.filter((locale) => {
      const isoCode = locale.split(/[-_]/)[0]?.toLowerCase();
      return ENABLED_LANGUAGE_ISO_CODES.has(isoCode);
    });

    if (filtered.length > 0) {
      return filtered;
    }

    return ['fr-fr', 'en-us'];
  }, [config?.LANGUAGES, i18n?.options?.resources]);

  const currentIsoLanguage = useMemo(() => {
    const sourceLanguage =
      i18n.resolvedLanguage ||
      i18n.language ||
      user?.language ||
      config?.LANGUAGE_CODE ||
      'fr';
    return toIsoCode(sourceLanguage);
  }, [
    i18n.resolvedLanguage,
    i18n.language,
    user?.language,
    config?.LANGUAGE_CODE,
  ]);

  const optionsPicker = useMemo(() => {
    const labels = new Map(config?.LANGUAGES ?? []);
    const byIsoCode = new Map<
      string,
      { label: string; value: string; shortLabel: string }
    >();

    for (const locale of availableLanguages) {
      const isoCode = toIsoCode(locale);
      if (!byIsoCode.has(isoCode)) {
        const label = labels.get(locale) ?? locale.toUpperCase();
        byIsoCode.set(isoCode, {
          label,
          value: toUiLocale(locale),
          shortLabel: isoCode.toUpperCase(),
        });
      }
    }

    const orderedOptions = Array.from(byIsoCode.entries()).map(
      ([, option]) => option,
    );
    orderedOptions.sort((a, b) => {
      if (toIsoCode(a.value) === currentIsoLanguage) return -1;
      if (toIsoCode(b.value) === currentIsoLanguage) return 1;
      return 0;
    });

    return orderedOptions;
  }, [availableLanguages, config?.LANGUAGES, currentIsoLanguage]);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      const currentLanguage = i18n.resolvedLanguage || i18n.language || 'en';
      document.documentElement.lang = toIsoCode(currentLanguage);
    }
  }, [i18n.language, i18n.resolvedLanguage]);

  return (
    <LanguagePickerUi
      key={currentIsoLanguage}
      languages={optionsPicker}
      size={size}
      compact={compact}
      {...(color !== undefined ? { color } : {})}
      onChange={(selected) => {
        type LanguageOption = { value?: string };
        let code: string | undefined;

        if (typeof selected === 'string') {
          code = selected;
        } else if (
          typeof selected === 'object' &&
          selected !== null &&
          typeof (selected as LanguageOption).value === 'string'
        ) {
          code = (selected as LanguageOption).value;
        }

        if (!code) {
          return;
        }

        changeLanguageSynchronized(code, user).catch((err) => {
          console.error('Error changing language', err);
        });
      }}
    />
  );
};
