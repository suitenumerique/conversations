import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

import { Box } from '@/components';

import { Toast, ToastType } from './CustomToast';

interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  icon?: string;
  duration?: number;
}

interface ToastContextType {
  showToast: (
    type: ToastType,
    message: string,
    icon?: string,
    duration?: number,
  ) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

interface ToastProviderProps {
  children: ReactNode;
}

export const ToastProvider = ({ children }: ToastProviderProps) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback(
    (type: ToastType, message: string, icon?: string, duration = 4000) => {
      const id = Math.random().toString(36).substr(2, 9);
      const newToast: ToastItem = { id, message, type, icon, duration };

      setToasts((prev) => [...prev, newToast]);
    },
    [],
  );

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const value = {
    showToast,
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      {typeof window !== 'undefined' &&
        createPortal(
          <Box
            $css={`
            position: fixed;
            top: 8px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1000;
            display: inline-block;
            flex-direction: column;
            gap: 8px;
            width: auto;
            pointer-events: none;
            & > * {
              pointer-events: auto;
            }
          `}
          >
            {toasts.map((toast) => (
              <Toast
                key={toast.id}
                id={toast.id}
                message={toast.message}
                type={toast.type}
                icon={toast.icon}
                duration={toast.duration}
                onClose={removeToast}
              />
            ))}
          </Box>,
          document.body,
        )}
    </ToastContext.Provider>
  );
};
