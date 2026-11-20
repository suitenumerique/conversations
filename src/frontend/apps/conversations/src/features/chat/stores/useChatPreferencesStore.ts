import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  themeModePreference: 'system' | 'light' | 'dark';
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  /** Slugs of the connectors forced for the next messages. */
  forcedConnectors: string[];
  isDarkModePreference: boolean;
  isPanelOpen: boolean;
  isSourcesPanelOpen: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  setThemeModePreference: (mode: 'system' | 'light' | 'dark') => void;
  toggleDarkModePreferences: () => void;
  toggleForceWebSearch: () => void;
  toggleForcedConnector: (slug: string) => void;
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
      toggleForcedConnector: (slug) =>
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
      // 1: `forceDatagouv: boolean` became `forcedConnectors: string[]`.
      version: 1,
      migrate: (persisted, version) => {
        const state = (persisted ?? {}) as Record<string, unknown>;
        if (version < 1) {
          const { forceDatagouv, ...rest } = state;
          return {
            ...rest,
            forcedConnectors: forceDatagouv ? ['datagouv'] : [],
          } as unknown as ChatPreferencesState;
        }
        return state as unknown as ChatPreferencesState;
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
