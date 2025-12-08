import { UseChatOptions, useChat as useAiSdkChat } from '@ai-sdk/react';

import { fetchAPI } from '@/api';
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

  const { forceWebSearch, selectedModelHrid, forcePlanMode } =
    useChatPreferencesStore.getState();

  if (forceWebSearch) {
    searchParams.append('force_web_search', 'true');
  }

  if (selectedModelHrid) {
    searchParams.append('model_hrid', selectedModelHrid);
  }

  if (forcePlanMode) {
    searchParams.append('force_plan', 'true');
  }

  if (searchParams.toString()) {
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}${searchParams.toString()}`;
  }

  return fetchAPI(url, init);
};

export function useChat(options: Omit<UseChatOptions, 'fetch'>) {
  return useAiSdkChat({
    ...options,
    maxSteps: 3,
    fetch: fetchAPIAdapter,
  });
}
