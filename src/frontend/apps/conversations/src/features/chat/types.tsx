import { Message } from '@ai-sdk/react';

export type ChatMessage = Message;

export interface ChatConversationProject {
  id: string;
  title: string;
  icon: string;
}

export interface ChatConversation {
  id: string;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
  title?: string;
  project?: ChatConversationProject | null;
  // True when the pinned model can't read images and the conversation has any
  // image (project or history). Backend-computed on read; drives the soft
  // "image processing unavailable" banner.
  images_skipped?: boolean;
}
export interface ChatProjectConversation {
  id: string;
  title?: string;
}

export interface ChatProject {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  icon: string;
  color: string;
  llm_instructions: string;
  conversations: ChatProjectConversation[];
}
