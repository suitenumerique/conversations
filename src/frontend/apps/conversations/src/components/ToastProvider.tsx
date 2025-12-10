import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
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
  actionLabel?: string;
  actionHref?: string;
}

interface ToastContextType {
  showToast: (
    type: ToastType,
    message: string,
    icon?: string,
    duration?: number,
    options?: { actionLabel?: string; actionHref?: string },
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
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const showToast = useCallback(
    (
      type: ToastType,
      message: string,
      icon?: string,
      duration = 4000,
      options?: { actionLabel?: string; actionHref?: string },
    ) => {
      const id = Math.random().toString(36).substr(2, 9);
      const newToast: ToastItem = {
        id,
        message,
        type,
        icon,
        duration,
        actionLabel: options?.actionLabel,
        actionHref: options?.actionHref,
      };

      setToasts((prev) => [newToast, ...prev]);
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
      {isMounted &&
        typeof document !== 'undefined' &&
        document.body &&
        createPortal(
          <Box
            aria-live="polite"
            $css={`
            position: fixed;
            top: 8px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1000;
            display: flex;
            flex-direction: column;
            width: auto;
            pointer-events: none;
            & > * {
              pointer-events: auto;
              margin-bottom: 8px;
              transition: transform 0.3s ease-out, margin 0.3s ease-out;
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
                actionLabel={toast.actionLabel}
                actionHref={toast.actionHref}
                onClose={removeToast}
              />
            ))}
          </Box>,
          document.body,
        )}
    </ToastContext.Provider>
  );
};
