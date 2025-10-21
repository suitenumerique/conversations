import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatPreferencesState {
  selectedModelHrid: string | null;
  forceWebSearch: boolean;
  isPanelOpen: boolean;
  selectedTools: string[];
  setSelectedModelHrid: (hrid: string | null) => void;
  toggleForceWebSearch: () => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
  toggleSelectedTool: (tool: string) => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      selectedModelHrid: null,
      forceWebSearch: false,
      isPanelOpen: false,
      selectedTools: [],
      setSelectedModelHrid: (hrid) => set({ selectedModelHrid: hrid }),
      toggleForceWebSearch: () =>
        set((state) => ({ forceWebSearch: !state.forceWebSearch })),
      setPanelOpen: (isOpen) => set({ isPanelOpen: isOpen }),
      togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
      toggleSelectedTool: (tool) =>
        set((state) => ({
          selectedTools: state.selectedTools.includes(tool)
            ? state.selectedTools.filter((t) => t !== tool)
            : [...state.selectedTools, tool],
        })),
    }),
    {
      name: 'chat-preferences',
    },
  ),
);
