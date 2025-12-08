import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  forcePlanMode: boolean;
  isPanelOpen: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  toggleForceWebSearch: () => void;
  toggleForcePlanMode: () => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      selectedModelHrid: null,
      forceWebSearch: false,
      forcePlanMode: false,
      isPanelOpen: false,
      setSelectedModelHrid: (hrid) => set({ selectedModelHrid: hrid }),
      toggleForceWebSearch: () =>
        set((state) => ({ forceWebSearch: !state.forceWebSearch })),
      toggleForcePlanMode: () =>
        set((state) => ({ forcePlanMode: !state.forcePlanMode })),
      setPanelOpen: (isOpen) => set({ isPanelOpen: isOpen }),
      togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
    }),
    {
      name: 'chat-preferences',
    },
  ),
);
