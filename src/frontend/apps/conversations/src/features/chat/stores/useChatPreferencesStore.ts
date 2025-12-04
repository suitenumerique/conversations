import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  isPanelOpen: boolean;
  customMcpServerUrl: string | null;
  setSelectedModelHrid: (hrid: string | null) => void;
  toggleForceWebSearch: () => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
  setCustomMcpServerUrl: (url: string | null) => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      selectedModelHrid: null,
      forceWebSearch: false,
      isPanelOpen: false,
      customMcpServerUrl: null,
      setSelectedModelHrid: (hrid) => set({ selectedModelHrid: hrid }),
      toggleForceWebSearch: () =>
        set((state) => ({ forceWebSearch: !state.forceWebSearch })),
      setPanelOpen: (isOpen) => set({ isPanelOpen: isOpen }),
      togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
      setCustomMcpServerUrl: (url) => set({ customMcpServerUrl: url }),
    }),
    {
      name: 'chat-preferences',
    },
  ),
);
