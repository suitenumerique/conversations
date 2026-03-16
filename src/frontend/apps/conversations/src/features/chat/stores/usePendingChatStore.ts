import { create } from 'zustand';

interface PendingChatState {
  input: string;
  files: FileList | null;
  projectId: string | null;
  setPendingChat: (input: string, files: FileList | null) => void;
  clearPendingChat: () => void;
  setProjectId: (projectId: string | null) => void;
}

export const usePendingChatStore = create<PendingChatState>((set) => ({
  input: '',
  files: null,
  projectId: null,
  setPendingChat: (input, files) => set({ input, files }),
  clearPendingChat: () => set({ input: '', files: null, projectId: null }),
  setProjectId: (projectId) => set({ projectId }),
}));
