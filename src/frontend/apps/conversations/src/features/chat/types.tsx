import { Message } from '@ai-sdk/react';

export type ChatMessage = Message;

export interface ChatConversation {
  id: string;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
  title?: string;
}
