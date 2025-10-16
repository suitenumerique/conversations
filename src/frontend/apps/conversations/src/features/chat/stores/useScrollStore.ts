import { create } from 'zustand';

interface ScrollState {
  isAtTop: boolean;
  setIsAtTop: (isAtTop: boolean) => void;
}

export const useScrollStore = create<ScrollState>((set) => ({
  isAtTop: true,
  setIsAtTop: (isAtTop) => set({ isAtTop }),
}));
