import { UIMessage } from 'ai';

export type ChatMessage = UIMessage;

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
  // Arena comparison still waiting for a vote. When `restorable` is true both
  // answers are complete and are returned in `answers`: the client puts the
  // split view back on screen so the choice survives a reload or a navigation
  // and is only ever closed by the user picking a side. When it is false the
  // comparison may still be streaming (in this page or another tab): the
  // client leaves it alone and shows the history as is; the backend resolves
  // it on the next message.
  pending_arena_comparison?: {
    id: string;
    sides_finished: { left: boolean; right: boolean };
    restorable: boolean;
    answers: { left: ChatMessage; right: ChatMessage } | null;
  } | null;
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
