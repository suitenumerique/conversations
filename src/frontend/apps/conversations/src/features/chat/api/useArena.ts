import { UIMessage } from 'ai';

import { APIError, errorCauses, fetchAPI } from '@/api';
import { ChatConversation } from '@/features/chat/types';

export type ArenaSide = 'left' | 'right';

export type ArenaDraw =
  { arena: false } | { arena: true; comparison_id: string };

const NO_ARENA: ArenaDraw = { arena: false };

/**
 * Ask the backend whether the next turn is an arena turn. Any failure is
 * treated as "no arena": the message is then sent through the normal path.
 */
export const drawArena = async (
  conversationId: string,
  forceWebSearch: boolean,
  message?: UIMessage,
  // The selected model: an unpinned conversation is pinned to it, as on a
  // normal first turn.
  modelHrid?: string | null,
  // Frozen with web search so both candidates run with the same connectors.
  forceDatagouv = false,
): Promise<ArenaDraw> => {
  try {
    const response = await fetchAPI(`chats/${conversationId}/arena/draw/`, {
      method: 'POST',
      body: JSON.stringify({
        force_web_search: forceWebSearch,
        force_datagouv: forceDatagouv || undefined,
        message,
        model_hrid: modelHrid || undefined,
      }),
    });
    if (!response.ok) {
      return NO_ARENA;
    }
    const data = (await response.json()) as Partial<ArenaDraw> | null;
    if (
      data?.arena === true &&
      typeof (data as { comparison_id?: unknown }).comparison_id === 'string'
    ) {
      return data as ArenaDraw;
    }
    return NO_ARENA;
  } catch {
    return NO_ARENA;
  }
};

/** Milestones the backend flags on a user's vote count. */
export type ArenaMilestone = 'first_vote' | 'tenth_vote' | 'hundredth_vote';

/** Figures returned with a vote, shown in the thanks card. */
export interface ArenaAcknowledgement {
  /** This user's votes on comparisons under 90 days. */
  user_votes: number;
  experiment_votes: number;
  milestone: ArenaMilestone | null;
}

export interface ArenaVoteResult {
  conversation: ChatConversation;
  /** `null` on abandonment, or when the backend sends none. */
  acknowledgement: ArenaAcknowledgement | null;
}

const isAcknowledgement = (value: unknown): value is ArenaAcknowledgement =>
  typeof value === 'object' &&
  value !== null &&
  typeof (value as ArenaAcknowledgement).user_votes === 'number' &&
  typeof (value as ArenaAcknowledgement).experiment_votes === 'number';

/**
 * Record the vote for a comparison: the displayed side the user preferred.
 * `side: null` abandons it (the backend keeps the production answer). Returns
 * the updated conversation and, for a real vote, the acknowledgement block.
 */
export const voteArena = async (
  conversationId: string,
  comparisonId: string,
  side: ArenaSide | null,
): Promise<ArenaVoteResult> => {
  const response = await fetchAPI(
    `chats/${conversationId}/arena/${comparisonId}/vote/`,
    {
      method: 'POST',
      body: JSON.stringify({ side }),
    },
  );
  if (!response.ok) {
    throw new APIError(
      'Failed to record the arena vote',
      await errorCauses(response),
    );
  }
  const { acknowledgement, ...conversation } =
    (await response.json()) as ChatConversation & { acknowledgement?: unknown };
  return {
    conversation,
    acknowledgement: isAcknowledgement(acknowledgement)
      ? acknowledgement
      : null,
  };
};
