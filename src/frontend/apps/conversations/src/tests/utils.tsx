import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PropsWithChildren, useState } from 'react';

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
      <CunninghamProvider theme="default">{children}</CunninghamProvider>
    </QueryClientProvider>
  );
};
