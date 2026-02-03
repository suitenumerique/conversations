import merge from 'lodash/merge';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { safeLocalStorage } from '@/utils/storages';

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
  isDarkMode: boolean;
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

// Helper to get isDarkMode from useChatPreferencesStore
const getIsDarkModeFromPreferences = (): boolean => {
  try {
    return useChatPreferencesStore.getState().isDarkModePreference ?? false;
  } catch {
    return false;
  }
};

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
  isDarkMode: getIsDarkModeFromPreferences(),
  toggleDarkMode: () => {},
};

export const useCunninghamTheme = create<ThemeStore>()(
  persist(
    (set) => ({
      ...initialState,
      setTheme: (theme: Theme) => {
        // Extract base theme (default or dsfr)
        const baseTheme: Theme =
          theme === 'dark' || theme === 'dsfr-dark'
            ? theme === 'dark'
              ? 'default'
              : 'dsfr'
            : theme;

        const isDarkMode =
          getIsDarkModeFromPreferences() ??
          (theme === 'dark' || theme === 'dsfr-dark');

        // Apply dark mode based on stored preference or theme
        const finalTheme: Theme = isDarkMode
          ? baseTheme === 'dsfr'
            ? 'dsfr-dark'
            : 'dark'
          : baseTheme;

        const newTokens = getMergedTokens(finalTheme);

        set({
          colorsTokens: newTokens.globals.colors,
          componentTokens: getComponentTokens(newTokens),
          contextualTokens: newTokens.contextuals,
          currentTokens: tokens.themes[finalTheme] as Partial<Tokens>,
          fontSizesTokens: newTokens.globals.font.sizes,
          spacingsTokens: newTokens.globals.spacings,
          theme: finalTheme,
          baseTheme,
          themeTokens: newTokens.globals,
          isDarkMode,
        });
      },
      toggleDarkMode: () => {
        useChatPreferencesStore.getState().toggleDarkModePreferences();

        set((state) => {
          const newIsDarkMode = getIsDarkModeFromPreferences();
          const newTheme: Theme = newIsDarkMode
            ? state.baseTheme === 'dsfr'
              ? 'dsfr-dark'
              : 'dark'
            : state.baseTheme;

          const newTokens = getMergedTokens(newTheme);

          return {
            colorsTokens: newTokens.globals.colors,
            componentTokens: getComponentTokens(newTokens),
            contextualTokens: newTokens.contextuals,
            currentTokens: tokens.themes[newTheme] as Partial<Tokens>,
            fontSizesTokens: newTokens.globals.font.sizes,
            spacingsTokens: newTokens.globals.spacings,
            theme: newTheme,
            baseTheme: state.baseTheme,
            themeTokens: newTokens.globals,
            isDarkMode: newIsDarkMode,
          };
        });
      },
    }),
    {
      name: 'cunningham-theme',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-assignment
      storage: safeLocalStorage as any,
      partialize: (state) => ({ isDarkMode: state.isDarkMode }),
      onRehydrateStorage: () => (state, error) => {
        if (error) {
          console.error('[useCunninghamTheme] Rehydration error:', error);
          return;
        }
        if (state) {
          state.isDarkMode = getIsDarkModeFromPreferences();
        }
      },
    },
  ),
);
