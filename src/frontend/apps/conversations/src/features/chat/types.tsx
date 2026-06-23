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
  // True when the conversation's pinned model can't read images and the parent
  // project has at least one image attachment. Backend-computed on read.
  project_images_skipped?: boolean;
  // Filenames of uploaded images across the whole conversation that the pinned
  // (text-only) model can't read. Backend-computed on read; empty when the model
  // is multimodal. Drives the conversation-scoped "images ignored" banner.
  skipped_image_names?: string[];
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
