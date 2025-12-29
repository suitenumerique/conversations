import { UseChatOptions, useChat as useAiSdkChat } from '@ai-sdk/react';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { fetchAPI } from '@/api';
import { KEY_LIST_CONVERSATION } from '@/features/chat/api/useConversations';
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
    item.type === 'conversation_metadata'
  );
}

export function useChat(options: Omit<UseChatOptions, 'fetch'>) {
  const queryClient = useQueryClient();

  const result = useAiSdkChat({
    ...options,
    maxSteps: 3,
    fetch: fetchAPIAdapter,
  });

  useEffect(() => {
    if (result.data && Array.isArray(result.data)) {
      for (const item of result.data) {
        if (isConversationMetadataEvent(item)) {
          void queryClient.invalidateQueries({
            queryKey: [KEY_LIST_CONVERSATION],
          });
        }
      }
    }
  }, [result.data, queryClient]);
  return result;
}
