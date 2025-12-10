import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import dynamic from 'next/dynamic';
import { useEffect } from 'react';

import { useCunninghamTheme } from '@/cunningham';
import { Auth, KEY_AUTH, setAuthUrl } from '@/features/auth';
import { useResponsiveStore } from '@/stores';

import { ConfigProvider } from './config';

// Client-only providers
const ToastProviderNoSSR = dynamic(
  () => import('@/components').then((mod) => ({ default: mod.ToastProvider })),
  { ssr: false, loading: () => null },
);

const CunninghamProviderNoSSR = dynamic(
  () =>
    import('@openfun/cunningham-react').then((mod) => ({
      default: mod.CunninghamProvider,
    })),
  { ssr: false },
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 1000 * 60 * 3, retry: 1 },
    mutations: {
      onError: (error) => {
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
