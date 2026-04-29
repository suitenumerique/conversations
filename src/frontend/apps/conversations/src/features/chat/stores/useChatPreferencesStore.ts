import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  themeModePreference: 'system' | 'light' | 'dark';
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  isDarkModePreference: boolean;
  isPanelOpen: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  setThemeModePreference: (mode: 'system' | 'light' | 'dark') => void;
  toggleDarkModePreferences: () => void;
  toggleForceWebSearch: () => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      themeModePreference: 'system',
      selectedModelHrid: null,
      forceWebSearch: false,
      isDarkModePreference: false,
      isPanelOpen: false,
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
      setPanelOpen: (isOpen) => set({ isPanelOpen: isOpen }),
      togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
    }),
    {
      name: 'chat-preferences',
    },
  ),
);
