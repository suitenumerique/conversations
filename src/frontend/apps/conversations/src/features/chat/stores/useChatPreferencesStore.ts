import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  toggleForceWebSearch: () => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      selectedModelHrid: null,
      forceWebSearch: false,
      setSelectedModelHrid: (hrid) => set({ selectedModelHrid: hrid }),
      toggleForceWebSearch: () =>
        set((state) => ({ forceWebSearch: !state.forceWebSearch })),
    }),
    {
      name: 'chat-preferences',
    },
  ),
);
