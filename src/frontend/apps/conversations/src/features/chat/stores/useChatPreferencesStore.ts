import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  themeModePreference: 'system' | 'light' | 'dark';
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  /** Slugs of the connectors forced for the next messages, until switched off. */
  forcedConnectors: string[];
  isDarkModePreference: boolean;
  isPanelOpen: boolean;
  isSourcesPanelOpen: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  setThemeModePreference: (mode: 'system' | 'light' | 'dark') => void;
  toggleDarkModePreferences: () => void;
  toggleForceWebSearch: () => void;
  toggleForceConnector: (slug: string) => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
  setSourcesPanelOpen: (isOpen: boolean) => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      themeModePreference: 'system',
      selectedModelHrid: null,
      forceWebSearch: false,
      forcedConnectors: [],
      isDarkModePreference: false,
      isPanelOpen: false,
      isSourcesPanelOpen: false,
      setSelectedModelHrid: (hrid) => set({ selectedModelHrid: hrid }),
      setThemeModePreference: (mode) =>
        set({
          themeModePreference: mode,
          isDarkModePreference: mode === 'dark',
        }),
      toggleDarkModePreferences: () =>
        set((state) => {
          const nextIsDarkMode = !state.isDarkModePreference;
          return {
            isDarkModePreference: nextIsDarkMode,
            themeModePreference: nextIsDarkMode ? 'dark' : 'light',
          };
        }),
      toggleForceWebSearch: () =>
        set((state) => ({ forceWebSearch: !state.forceWebSearch })),
      toggleForceConnector: (slug) =>
        set((state) => ({
          forcedConnectors: state.forcedConnectors.includes(slug)
            ? state.forcedConnectors.filter((forced) => forced !== slug)
            : [...state.forcedConnectors, slug],
        })),
      setPanelOpen: (isOpen) => set({ isPanelOpen: isOpen }),
      togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
      setSourcesPanelOpen: (isOpen) => set({ isSourcesPanelOpen: isOpen }),
    }),
    {
      name: 'chat-preferences',
      // 1: the data.gouv-only `forceDatagouv` became `forcedConnectors`.
      version: 1,
      migrate: (persisted, version) => {
        const state = (persisted ?? {}) as Record<string, unknown>;
        if (version < 1) {
          const { forceDatagouv, ...rest } = state;
          return {
            ...rest,
            forcedConnectors: forceDatagouv === true ? ['datagouv'] : [],
          };
        }
        return state;
      },
      partialize: (state) => ({
        themeModePreference: state.themeModePreference,
        selectedModelHrid: state.selectedModelHrid,
        forceWebSearch: state.forceWebSearch,
        forcedConnectors: state.forcedConnectors,
        isDarkModePreference: state.isDarkModePreference,
        isPanelOpen: state.isPanelOpen,
      }),
    },
  ),
);
