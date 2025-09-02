import { UseChatOptions, useChat as useAiSdkChat } from '@ai-sdk/react';

import { fetchAPI } from '@/api';

// Adapter to match the global fetch signature
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

  // Add force_web_search parameter if it's globally enabled
  if ((window as { globalForceWebSearch?: boolean }).globalForceWebSearch) {
    // For relative URLs, just append the parameter
    if (url.startsWith('http')) {
      const urlObj = new URL(url);
      urlObj.searchParams.set('force_web_search', 'true');
      url = urlObj.toString();
    } else {
      // For relative URLs, append the parameter manually
      const separator = url.includes('?') ? '&' : '?';
      url = `${url}${separator}force_web_search=true`;
    }
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
