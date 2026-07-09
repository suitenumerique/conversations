import { UseChatOptions, useChat as useAiSdkChat } from '@ai-sdk/react';
import { Message } from '@ai-sdk/ui-utils';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { fetchAPI } from '@/api';
import { KEY_LIST_CONVERSATION } from '@/features/chat/api/useConversations';
import { KEY_LIST_PROJECT } from '@/features/chat/api/useProjects';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

const fetchAPIAdapter = (input: RequestInfo | URL, init?: RequestInit) => {
  let url: string;
  if (typeof input === 'string') {
    url = input;
  } else if (input instanceof URL) {
    url = input.toString();
  } else if (input instanceof Request) {
    url = input.url;
  } else {
    throw new Error('Unsupported input type for fetchAPIAdapter');
  }

  const searchParams = new URLSearchParams();

  const { forceWebSearch, selectedModelHrid } =
    useChatPreferencesStore.getState();

  if (forceWebSearch) {
    searchParams.append('force_web_search', 'true');
  }

  if (selectedModelHrid) {
    searchParams.append('model_hrid', selectedModelHrid);
  }

  if (searchParams.toString()) {
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}${searchParams.toString()}`;
  }

  return fetchAPI(url, init);
};

interface ConversationMetadataEvent {
  type: 'conversation_metadata';
  conversationId: string;
  title: string;
}
// Type guard to check if an item is a ConversationMetadataEvent
function isConversationMetadataEvent(
  item: unknown,
): item is ConversationMetadataEvent {
  return (
    typeof item === 'object' &&
    item !== null &&
    'type' in item &&
    item.type === 'conversation_metadata' &&
    'conversationId' in item &&
    typeof item.conversationId === 'string' &&
    'title' in item &&
    typeof item.title === 'string'
  );
}

interface CooldownEvent {
  type: 'cooldown';
  seconds: number;
}
// Inference-load cooldown emitted at the end of a response: the client should
// wait `seconds` before sending the next message.
function isCooldownEvent(item: unknown): item is CooldownEvent {
  return (
    typeof item === 'object' &&
    item !== null &&
    'type' in item &&
    item.type === 'cooldown' &&
    'seconds' in item &&
    typeof (item as CooldownEvent).seconds === 'number'
  );
}

async function fetchChatCooldown(): Promise<{ cooldown_seconds: number }> {
  const response = await fetchAPI('chat-cooldown/');
  if (!response.ok) {
    throw new Error('Failed to fetch chat cooldown');
  }
  return response.json() as Promise<{ cooldown_seconds: number }>;
}

// Stream-protocol contract with the backend. Mirrored in
// ``pydantic_ai.py`` (``IMAGES_SKIPPED_EVENT_TYPE`` /
// ``IMAGE_SKIP_REASON_TEXT_ONLY``). Keep both sides in sync when adding new
// reasons or events.
export const IMAGES_SKIPPED_EVENT_TYPE = 'images_skipped' as const;
export const IMAGE_SKIP_REASON_TEXT_ONLY = 'model_text_only' as const;

export type ImagesSkippedEventKind = 'chat_notice' | 'last_message_marked';

export interface ImagesSkippedEvent {
  type: typeof IMAGES_SKIPPED_EVENT_TYPE;
  kind: ImagesSkippedEventKind;
  reason: string;
}

export function isImagesSkippedEvent(
  item: unknown,
): item is ImagesSkippedEvent {
  return (
    typeof item === 'object' &&
    item !== null &&
    'type' in item &&
    item.type === IMAGES_SKIPPED_EVENT_TYPE &&
    'kind' in item &&
    ((item as ImagesSkippedEvent).kind === 'chat_notice' ||
      (item as ImagesSkippedEvent).kind === 'last_message_marked')
  );
}

/**
 * Stamp `skipped: { reason: <IMAGE_SKIP_REASON_TEXT_ONLY> }` on every image-like
 * attachment of the latest user message, returning the same array reference
 * when nothing changed. Used to mark optimistic attachments live when the
 * backend signals it skipped them (mirroring the persisted-state behaviour).
 */
export function stampImagesSkippedOnLatestUserMessage(
  prevMessages: Message[],
): Message[] {
  const lastUserIdx = prevMessages.findLastIndex((m) => m.role === 'user');
  if (lastUserIdx === -1) return prevMessages;
  const lastUser = prevMessages[lastUserIdx];
  const attachments = lastUser.experimental_attachments;
  if (!attachments || attachments.length === 0) return prevMessages;
  let mutated = false;
  const updated = attachments.map((att) => {
    if (
      att.contentType?.startsWith('image/') &&
      !(att as { skipped?: unknown }).skipped
    ) {
      mutated = true;
      return { ...att, skipped: { reason: IMAGE_SKIP_REASON_TEXT_ONLY } };
    }
    return att;
  });
  if (!mutated) return prevMessages;
  const next = [...prevMessages];
  next[lastUserIdx] = {
    ...lastUser,
    experimental_attachments: updated,
  };
  return next;
}

export function useChat(options: Omit<UseChatOptions, 'fetch'>) {
  const queryClient = useQueryClient();

  const result = useAiSdkChat({
    ...options,
    maxSteps: 3,
    fetch: fetchAPIAdapter,
  });

  // Epoch ms until which the user must wait before sending a new message.
  const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);
  // Track how many data items we have already handled so each event is
  // processed exactly once (the data stream grows append-only).
  const processedCountRef = useRef(0);

  // Restore the cooldown from the backend (the authoritative source) so it
  // survives a refresh, a new tab, or switching conversations. react-query
  // refetches on mount and on window focus, keeping tabs in sync.
  const { data: cooldownData } = useQuery({
    queryKey: ['chat-cooldown'],
    queryFn: fetchChatCooldown,
  });

  useEffect(() => {
    if (!cooldownData) {
      return;
    }
    setCooldownUntil(
      cooldownData.cooldown_seconds > 0
        ? Date.now() + cooldownData.cooldown_seconds * 1000
        : null,
    );
  }, [cooldownData]);

  useEffect(() => {
    const data = result.data;
    if (!Array.isArray(data)) {
      processedCountRef.current = 0;
      return;
    }
    // Stream reset (e.g. switching conversations): reprocess from the start.
    if (data.length < processedCountRef.current) {
      processedCountRef.current = 0;
    }
    for (let i = processedCountRef.current; i < data.length; i++) {
      const item = data[i];
      if (isConversationMetadataEvent(item)) {
        void queryClient.invalidateQueries({
          queryKey: [KEY_LIST_CONVERSATION],
        });
        void queryClient.invalidateQueries({
          queryKey: [KEY_LIST_PROJECT],
        });
      } else if (isCooldownEvent(item)) {
        setCooldownUntil(Date.now() + item.seconds * 1000);
      }
    }
    processedCountRef.current = data.length;
  }, [result.data, queryClient]);

  return { ...result, cooldownUntil };
}
