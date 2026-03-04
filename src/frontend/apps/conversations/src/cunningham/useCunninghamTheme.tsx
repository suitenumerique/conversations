import merge from 'lodash/merge';
import { create } from 'zustand';

import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

import { tokens } from './cunningham-tokens';

type Tokens = typeof tokens.themes.default &
  Partial<(typeof tokens.themes)[keyof typeof tokens.themes]>;
type ColorsTokens = Tokens['globals']['colors'];
type FontSizesTokens = Tokens['globals']['font']['sizes'];
type SpacingsTokens = Tokens['globals']['spacings'];
type ComponentTokens = Partial<
  | (Tokens['components'] & Tokens['globals']['components'])
  | Record<string, unknown>
> &
  Record<string, unknown>;
type ContextualTokens = Tokens['contextuals'];
export type Theme = keyof typeof tokens.themes;

interface ThemeStore {
  colorsTokens: Partial<ColorsTokens>;
  componentTokens: ComponentTokens;
  contextualTokens: ContextualTokens;
  currentTokens: Partial<Tokens>;
  fontSizesTokens: Partial<FontSizesTokens>;
  setTheme: (theme: Theme) => void;
  spacingsTokens: Partial<SpacingsTokens>;
  theme: Theme;
  baseTheme: Theme; // 'default' or 'dsfr' (not persisted)
  themeTokens: Partial<Tokens['globals']>;
  toggleDarkMode: () => void;
}

const getMergedTokens = (theme: Theme) => {
  return merge({}, tokens.themes['default'], tokens.themes[theme]);
};

const getComponentTokens = (
  mergedTokens: ReturnType<typeof getMergedTokens>,
) => {
  // Merge components from root level (favicon, etc.) and globals.components (logo, etc.)
  return merge(
    {},
    mergedTokens.components || {},
    mergedTokens.globals?.components || {},
  );
};

const DEFAULT_THEME: Theme = 'default';
const defaultTokens = getMergedTokens(DEFAULT_THEME);

const initialState: ThemeStore = {
  colorsTokens: defaultTokens.globals.colors,
  componentTokens: getComponentTokens(defaultTokens),
  contextualTokens: defaultTokens.contextuals,
  currentTokens: tokens.themes[DEFAULT_THEME] as Partial<Tokens>,
  fontSizesTokens: defaultTokens.globals.font.sizes,
  setTheme: () => {},
  spacingsTokens: defaultTokens.globals.spacings,
  theme: DEFAULT_THEME,
  baseTheme: DEFAULT_THEME,
  themeTokens: defaultTokens.globals,
  toggleDarkMode: () => {},
};

const getIsDarkMode = () =>
  useChatPreferencesStore.getState().isDarkModePreference;

const resolveTheme = (baseTheme: Theme, isDarkMode: boolean): Theme =>
  isDarkMode ? (baseTheme === 'dsfr' ? 'dsfr-dark' : 'dark') : baseTheme;

const computeThemeState = (baseTheme: Theme, isDarkMode: boolean) => {
  const theme = resolveTheme(baseTheme, isDarkMode);
  const mergedTokens = getMergedTokens(theme);
  return {
    colorsTokens: mergedTokens.globals.colors,
    componentTokens: getComponentTokens(mergedTokens),
    contextualTokens: mergedTokens.contextuals,
    currentTokens: tokens.themes[theme] as Partial<Tokens>,
    fontSizesTokens: mergedTokens.globals.font.sizes,
    spacingsTokens: mergedTokens.globals.spacings,
    theme,
    baseTheme,
    themeTokens: mergedTokens.globals,
  };
};

export const useCunninghamTheme = create<ThemeStore>()((set) => ({
  ...initialState,
  setTheme: (theme: Theme) => {
    const baseTheme: Theme =
      theme === 'dark' || theme === 'dsfr-dark'
        ? theme === 'dark'
          ? 'default'
          : 'dsfr'
        : theme;

    set(computeThemeState(baseTheme, getIsDarkMode()));
  },
  toggleDarkMode: () => {
    useChatPreferencesStore.getState().toggleDarkModePreferences();

    set((state) => computeThemeState(state.baseTheme, getIsDarkMode()));
  },
}));
