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

export type TranscribeAudioResponse =
  | {
      text: string;
    }
  | {
      error: string;
    };
