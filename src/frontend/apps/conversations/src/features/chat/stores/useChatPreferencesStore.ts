import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  themeModePreference: 'system' | 'light' | 'dark';
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  forceDatagouv: boolean;
  isDarkModePreference: boolean;
  isPanelOpen: boolean;
  isSourcesPanelOpen: boolean;
  /** Whether the one-line arena intro has already been shown once. */
  hasSeenArenaIntro: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  setThemeModePreference: (mode: 'system' | 'light' | 'dark') => void;
  toggleDarkModePreferences: () => void;
  toggleForceWebSearch: () => void;
  toggleForceDatagouv: () => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
  setSourcesPanelOpen: (isOpen: boolean) => void;
  markArenaIntroSeen: () => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      themeModePreference: 'system',
      selectedModelHrid: null,
      forceWebSearch: false,
      forceDatagouv: false,
      isDarkModePreference: false,
      isPanelOpen: false,
      isSourcesPanelOpen: false,
      hasSeenArenaIntro: false,
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
      toggleForceDatagouv: () =>
        set((state) => ({ forceDatagouv: !state.forceDatagouv })),
      setPanelOpen: (isOpen) => set({ isPanelOpen: isOpen }),
      togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
      setSourcesPanelOpen: (isOpen) => set({ isSourcesPanelOpen: isOpen }),
      markArenaIntroSeen: () => set({ hasSeenArenaIntro: true }),
    }),
    {
      name: 'chat-preferences',
      partialize: (state) => ({
        themeModePreference: state.themeModePreference,
        selectedModelHrid: state.selectedModelHrid,
        forceWebSearch: state.forceWebSearch,
        forceDatagouv: state.forceDatagouv,
        isDarkModePreference: state.isDarkModePreference,
        isPanelOpen: state.isPanelOpen,
        hasSeenArenaIntro: state.hasSeenArenaIntro,
      }),
    },
  ),
);
