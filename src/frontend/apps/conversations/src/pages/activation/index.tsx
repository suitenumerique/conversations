import { useEffect } from 'react';
import { useNavigate } from 'react-router';

import { ActivationPage, useAuth } from '@/features/auth';

const Page = () => {
  const { authenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && !authenticated) {
      void navigate('/', { replace: true });
    }
  }, [authenticated, isLoading, navigate]);

  if (isLoading || !authenticated) {
    return null;
  }

  return <ActivationPage />;
};

export default Page;
