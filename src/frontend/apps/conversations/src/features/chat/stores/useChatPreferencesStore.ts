import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  isDarkModePreference: boolean;
  isPanelOpen: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  toggleDarkModePreferences: () => void;
  toggleForceWebSearch: () => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      selectedModelHrid: null,
      forceWebSearch: false,
      isDarkModePreference: false,
      isPanelOpen: false,
      setSelectedModelHrid: (hrid) => set({ selectedModelHrid: hrid }),
      toggleDarkModePreferences: () =>
        set((state) => ({ isDarkModePreference: !state.isDarkModePreference })),
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
