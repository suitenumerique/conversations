import { useEffect, useState } from 'react';

import { fetchAPI } from '@/api';

export function useToolProgress({
  conversationId,
  toolName,
  enabled,
  pollIntervalMs = 1000,
}: {
  conversationId: string | undefined;
  toolName: string | undefined | null;
  enabled: boolean;
  pollIntervalMs?: number;
}) {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !conversationId || !toolName) {
      setMessage(null);
      return;
    }

    let cancelled = false;
    let intervalId: number | undefined;

    const fetchProgress = async () => {
      try {
        const response = await fetchAPI(
          `chats/${conversationId}/tool-progress/${encodeURIComponent(toolName)}/`,
        );
        if (!response.ok) return;
        const data: { message: string | null } = await response.json();
        if (cancelled) return;
        setMessage(data?.message ?? null);
      } catch {
        // Polling must never break the chat UI.
      }
    };

    void fetchProgress();
    intervalId = window.setInterval(() => {
      void fetchProgress();
    }, pollIntervalMs);

    return () => {
      cancelled = true;
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [conversationId, toolName, enabled, pollIntervalMs]);

  return message;
}

