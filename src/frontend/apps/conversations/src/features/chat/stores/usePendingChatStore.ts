import { create } from 'zustand';

interface PendingChatState {
  input: string;
  files: FileList | null;
  setPendingChat: (input: string, files: FileList | null) => void;
  clearPendingChat: () => void;
}

export const usePendingChatStore = create<PendingChatState>((set) => ({
  input: '',
  files: null,
  setPendingChat: (input, files) => set({ input, files }),
  clearPendingChat: () => set({ input: '', files: null }),
}));
