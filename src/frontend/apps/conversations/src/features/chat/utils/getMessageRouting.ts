import { UIMessage } from 'ai';

import { RoutingEvent, isRoutingEvent } from '@/features/chat/api/useChat';

/**
 * Router fields persisted with an assistant message, next to `co2_impact`.
 * All optional: older messages and non-routed turns carry none.
 */
interface RoutingMetadata {
  tier?: string;
  tier_source?: string;
}

/**
 * The routing decision to show with an assistant message: the live stream
 * event when the turn was streamed in this session, otherwise the persisted
 * metadata (after a reload). `undefined` when the turn was not routed.
 */
export const getMessageRouting = (
  message: UIMessage,
  liveEvent?: RoutingEvent,
): RoutingEvent | undefined => {
  if (liveEvent) {
    return liveEvent;
  }
  const metadata = message.metadata;
  if (typeof metadata !== 'object' || metadata === null) {
    return undefined;
  }
  const { tier, tier_source } = metadata as RoutingMetadata;
  const candidate = { tier, tier_source };
  return isRoutingEvent(candidate) ? candidate : undefined;
};
