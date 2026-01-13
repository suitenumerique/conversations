import { useCallback, useState } from 'react';

interface UseModalReturn {
  isOpen: boolean;
  open: () => void;
  close: () => void;
}

/**
 * Manages modal open/close state with stable callback references.
 *
 * @param initialState - Initial open state (default: false)
 * @returns `isOpen` state and stable `open`/`close` callbacks safe for dependency arrays
 *
 */
export const useOwnModal = (initialState = false): UseModalReturn => {
  const [isOpen, setIsOpen] = useState(initialState);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  return { isOpen, open, close };
};
