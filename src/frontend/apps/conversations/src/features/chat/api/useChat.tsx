import { useChat as useAiSdkChat } from '@ai-sdk/react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChatOnDataCallback,
  DefaultChatTransport,
  FileUIPart,
  UIMessage,
} from 'ai';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { fetchAPI } from '@/api';
import { KEY_CONVERSATION } from '@/features/chat/api/useConversation';
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

  // Read at request time, not at render time: the transport is built once but
  // these preferences change between messages.
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

/** A file part the backend kept on the message but hid from the model. */
export type SkippableFileUIPart = FileUIPart & {
  skipped?: { reason: string };
};

const isImageFilePart = (
  part: UIMessage['parts'][number],
): part is SkippableFileUIPart =>
  part.type === 'file' && part.mediaType.startsWith('image/');

/**
 * Stamp `skipped: { reason: <IMAGE_SKIP_REASON_TEXT_ONLY> }` on every image file
 * part of the latest user message, returning the same array reference when
 * nothing changed. Used to mark optimistic attachments live when the backend
 * signals it skipped them (mirroring the persisted-state behaviour).
 */
export function stampImagesSkippedOnLatestUserMessage(
  prevMessages: UIMessage[],
): UIMessage[] {
  const lastUserIdx = prevMessages.findLastIndex((m) => m.role === 'user');
  if (lastUserIdx === -1) return prevMessages;
  const lastUser = prevMessages[lastUserIdx];
  let mutated = false;
  const parts = lastUser.parts.map((part) => {
    if (isImageFilePart(part) && !part.skipped) {
      mutated = true;
      return { ...part, skipped: { reason: IMAGE_SKIP_REASON_TEXT_ONLY } };
    }
    return part;
  });
  if (!mutated) return prevMessages;
  const next = [...prevMessages];
  next[lastUserIdx] = { ...lastUser, parts };
  return next;
}

export interface UseChatOptions {
  /** Conversation id; changing it starts a fresh chat. */
  id?: string;
  /** Messages the chat starts with. */
  messages?: UIMessage[];
  /** Endpoint the transport posts to. */
  api: string;
  onError?: (error: Error) => void;
  /** Called for each `images_skipped` notice streamed by the backend. */
  onImagesSkipped?: (kind: ImagesSkippedEventKind) => void;
}

export function useChat({ api, onImagesSkipped, ...options }: UseChatOptions) {
  const queryClient = useQueryClient();
  // Epoch ms until which the user must wait before sending a new message.
  const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);

  // The transport is captured when the chat is created, so the callbacks it
  // ends up holding must always reach the latest render's handlers.
  const onImagesSkippedRef = useRef(onImagesSkipped);
  onImagesSkippedRef.current = onImagesSkipped;

  const transport = useMemo(
    () => new DefaultChatTransport({ api, fetch: fetchAPIAdapter }),
    [api],
  );

  const onData = useCallback<ChatOnDataCallback<UIMessage>>(
    (part) => {
      const item = part.data;
      if (isConversationMetadataEvent(item)) {
        void queryClient.invalidateQueries({
          queryKey: [KEY_LIST_CONVERSATION],
        });
        void queryClient.invalidateQueries({
          queryKey: [KEY_LIST_PROJECT],
        });
        void queryClient.invalidateQueries({
          queryKey: [KEY_CONVERSATION, item.conversationId],
        });
      } else if (isCooldownEvent(item)) {
        setCooldownUntil(Date.now() + item.seconds * 1000);
      } else if (isImagesSkippedEvent(item)) {
        onImagesSkippedRef.current?.(item.kind);
      }
    },
    [queryClient],
  );

  // No `sendAutomaticallyWhen`: every tool loop runs server-side inside the
  // agent and we register no client-side tool, so there is nothing for the
  // client to continue. Auto-resubmitting would hide a failure — an interrupted
  // turn looks like a resolved tool invocation with no trailing step, and the
  // resubmit flips the status away from `error` while the backend answers an
  // assistant-terminated message list with an empty stream: the bubble stays
  // blank instead of showing an error and a retry.
  const result = useAiSdkChat({ ...options, transport, onData });

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

  return { ...result, cooldownUntil };
}
