import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { TierSlug } from '@/features/chat/types';

interface ChatPreferencesState {
  themeModePreference: 'system' | 'light' | 'dark';
  selectedModelHrid: string | null;
  /**
   * Router tier of the current conversation, sent as `tier` when the router is
   * on. Not persisted: it applies to one conversation and goes back to `auto`
   * on a new one.
   */
  selectedTier: TierSlug;
  /**
   * Conversation `selectedTier` was picked for; `null` on the new-chat screen,
   * where the pin waits for the conversation the first message creates. What
   * makes the reset to `auto` fire on *another* conversation only, rather than
   * on any re-run of the loader (the new-conversation handoff remounts the
   * chat, which would drop the tier the user had just picked).
   */
  tierConversationId: string | null;
  forceWebSearch: boolean;
  forceDatagouv: boolean;
  isDarkModePreference: boolean;
  isPanelOpen: boolean;
  isSourcesPanelOpen: boolean;
  /** Whether the one-line router intro has already been shown once. */
  hasSeenRouterIntro: boolean;
  setSelectedModelHrid: (hrid: string | null) => void;
  /**
   * Pins a tier. `conversationId` says which conversation it belongs to;
   * omitted, the current owner is kept (releasing a pin inside a conversation).
   */
  setSelectedTier: (tier: TierSlug, conversationId?: string | null) => void;
  /** Hands the pending pin to the conversation the first message just created. */
  adoptTierConversation: (conversationId: string) => void;
  setThemeModePreference: (mode: 'system' | 'light' | 'dark') => void;
  toggleDarkModePreferences: () => void;
  toggleForceWebSearch: () => void;
  toggleForceDatagouv: () => void;
  setPanelOpen: (isOpen: boolean) => void;
  togglePanel: () => void;
  setSourcesPanelOpen: (isOpen: boolean) => void;
  markRouterIntroSeen: () => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      themeModePreference: 'system',
      selectedModelHrid: null,
      selectedTier: 'auto',
      tierConversationId: null,
      forceWebSearch: false,
      forceDatagouv: false,
      isDarkModePreference: false,
      isPanelOpen: false,
      isSourcesPanelOpen: false,
      hasSeenRouterIntro: false,
      setSelectedModelHrid: (hrid) => set({ selectedModelHrid: hrid }),
      setSelectedTier: (tier, conversationId) =>
        set((state) => ({
          selectedTier: tier,
          tierConversationId:
            conversationId === undefined
              ? state.tierConversationId
              : conversationId,
        })),
      adoptTierConversation: (conversationId) =>
        set({ tierConversationId: conversationId }),
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
      markRouterIntroSeen: () => set({ hasSeenRouterIntro: true }),
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
        hasSeenRouterIntro: state.hasSeenRouterIntro,
      }),
    },
  ),
);
