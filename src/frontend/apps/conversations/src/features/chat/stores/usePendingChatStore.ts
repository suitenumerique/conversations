import { create } from 'zustand';

interface PendingChatState {
  input: string;
  files: FileList | null;
  projectId: string | null;
  hasProjectInstructions: boolean;
  setPendingChat: (input: string, files: FileList | null) => void;
  setProjectId: (id: string | null) => void;
  setHasProjectInstructions: (value: boolean) => void;
  clearPendingInput: () => void;
  clearPendingChat: () => void;
}

export const usePendingChatStore = create<PendingChatState>((set) => ({
  input: '',
  files: null,
  projectId: null,
  hasProjectInstructions: false,
  setPendingChat: (input, files) => set({ input, files }),
  setProjectId: (id) => set({ projectId: id }),
  setHasProjectInstructions: (value) => set({ hasProjectInstructions: value }),
  clearPendingInput: () =>
    set({
      input: '',
      files: null,
      hasProjectInstructions: false,
    }),
  clearPendingChat: () =>
    set({
      input: '',
      files: null,
      projectId: null,
      hasProjectInstructions: false,
    }),
}));
