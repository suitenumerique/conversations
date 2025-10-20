import { useRouter } from 'next/router';
import { useEffect } from 'react';

import { ActivationPage, useAuth } from '@/features/auth';
import { NextPageWithLayout } from '@/types/next';

const Page: NextPageWithLayout = () => {
  const { authenticated, isLoading } = useAuth();
  const { replace } = useRouter();

  useEffect(() => {
    if (!isLoading && !authenticated) {
      void replace('/');
    }
  }, [authenticated, isLoading, replace]);

  if (isLoading || !authenticated) {
    return null;
  }

  return <ActivationPage />;
};

export default Page;
