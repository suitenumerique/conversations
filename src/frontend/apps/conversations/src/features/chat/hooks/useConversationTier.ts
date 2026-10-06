import { useEffect } from 'react';

import { TierSlug, isTierSlug } from '@/features/chat/types';

import { useChatPreferencesStore } from '../stores/useChatPreferencesStore';

/**
 * Keeps the tier pick of the chat tied to the conversation it was made in.
 *
 * @returns The tier selection handler, `undefined` while the `router` feature
 * flag is off (the model selector shows instead).
 */
export const useConversationTier = ({
  initialConversationId,
  conversationId,
  routerEnabled,
}: {
  initialConversationId: string | undefined;
  conversationId: string | undefined;
  routerEnabled: boolean;
}) => {
  const setSelectedTier = useChatPreferencesStore(
    (state) => state.setSelectedTier,
  );

  const handleTierSelect = (tier: TierSlug) => {
    // The pin belongs to the conversation it was made in; `null` on the
    // new-chat screen, where it is handed over once the conversation exists.
    setSelectedTier(tier, conversationId ?? null);
  };

  // A tier choice applies to one conversation: opening another one (or the
  // new-chat screen) goes back to Auto, until the loaded conversation restores
  // its own pin (see restorePinnedTier). Keyed on the conversation the pin was
  // made for, not on this effect running: the new-conversation handoff remounts
  // the chat with the id it just created, and the pin travels with it.
  useEffect(() => {
    const { tierConversationId } = useChatPreferencesStore.getState();
    if (tierConversationId !== (initialConversationId ?? null)) {
      setSelectedTier('auto', initialConversationId ?? null);
    }
  }, [initialConversationId, setSelectedTier]);

  return routerEnabled ? handleTierSelect : undefined;
};

/**
 * Show a loaded conversation's pin again (a reload or a switch lands on Auto
 * first), so the next turn keeps it instead of releasing it. Never over a turn
 * already sent or a tier picked meanwhile.
 */
export const restorePinnedTier = (
  pinnedTier: unknown,
  conversationId: string,
  hasSent: boolean,
) => {
  const { selectedTier, setSelectedTier } = useChatPreferencesStore.getState();
  if (!hasSent && isTierSlug(pinnedTier) && selectedTier === 'auto') {
    setSelectedTier(pinnedTier, conversationId);
  }
};
