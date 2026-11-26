import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PropsWithChildren, useState } from 'react';

import { CunninghamLocaleProvider } from '@/core/CunninghamLocaleProvider';
import '@/i18n/initI18n';

export const AppWrapper = ({ children }: PropsWithChildren) => {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <CunninghamLocaleProvider theme="default">
        {children}
      </CunninghamLocaleProvider>
    </QueryClientProvider>
  );
};
