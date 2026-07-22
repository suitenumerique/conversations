import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router';

import '@/i18n/initI18n';

export const AppWrapper = ({ children }: PropsWithChildren) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <CunninghamProvider theme="default">{children}</CunninghamProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
};
