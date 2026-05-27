import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import dynamic from 'next/dynamic';
import { useEffect } from 'react';

import { isAPIError } from '@/api';
import { useCunninghamTheme } from '@/cunningham';
import { Auth, KEY_AUTH, setAuthUrl } from '@/features/auth';
import { useResponsiveStore } from '@/stores';

import { ConfigProvider } from './config';
import { KEY_CONFIG } from './config/api/useConfig';

// Client-only providers
const ToastProviderNoSSR = dynamic(
  () => import('@/components').then((mod) => ({ default: mod.ToastProvider })),
  { ssr: false, loading: () => null },
);

const CunninghamProviderNoSSR = dynamic(
  () =>
    import('@gouvfr-lasuite/cunningham-react').then((mod) => ({
      default: mod.CunninghamProvider,
    })),
  { ssr: false },
);

const isMaintenanceError = (error: unknown): boolean =>
  isAPIError(error) &&
  error.status === 503 &&
  (error.cause?.includes('maintenance_mode') ?? false);

// Fires for BOTH queries and mutations: refresh /config/ as soon as any call
// reports maintenance mode so the SPA flips to the maintenance page.
const onAnyError = (error: unknown) => {
  if (isMaintenanceError(error)) {
    void queryClient.invalidateQueries({ queryKey: [KEY_CONFIG] });
  }
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 1000 * 60 * 3, retry: 1 },
    mutations: {
      onError: (error) => {
        onAnyError(error);
        // Mutations-only: a 401 here means an authenticated action was
        // rejected — bounce the user to the login wall. Queries deliberately
        // do not trigger this (a 401 on useAuthQuery is the normal logged-out
        // state and must not redirect, otherwise /401 → useAuthQuery → /401
        // becomes an infinite loop).
        if (
          error instanceof Error &&
          'status' in error &&
          error.status === 401
        ) {
          void queryClient.resetQueries({ queryKey: [KEY_AUTH] });
          setAuthUrl();
          if (typeof window !== 'undefined') {
            window.location.href = '/401';
          }
        }
      },
    },
  },
  queryCache: new QueryCache({ onError: onAnyError }),
});

export function AppProvider({ children }: { children: React.ReactNode }) {
  const theme = useCunninghamTheme((state) => state.theme);

  useEffect(() => {
    return useResponsiveStore.getState().initializeResizeListener();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <CunninghamProviderNoSSR theme={theme}>
        <ConfigProvider>
          <ToastProviderNoSSR>
            <Auth>{children}</Auth>
          </ToastProviderNoSSR>
        </ConfigProvider>
      </CunninghamProviderNoSSR>
    </QueryClientProvider>
  );
}
