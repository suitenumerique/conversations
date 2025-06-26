import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

import { useAnalytics } from '@/libs';

import { useAuthQuery } from '../api';

const regexpUrlsAuth = [
  /\/chat\/$/g, // New conversation requires authentication
  /\/chat$/g,
  /\/chat\/.+$/g, // Conversation requires authentication: remove to allow anonymous access
  /^\/$/g, // Root requires authentication
];

export const useAuth = () => {
  const { data: user, ...authStates } = useAuthQuery();
  const { pathname } = useRouter();
  const { trackEvent } = useAnalytics();
  const [hasTracked, setHasTracked] = useState(authStates.isFetched);
  const [pathAllowed, setPathAllowed] = useState<boolean>(
    !regexpUrlsAuth.some((regexp) => !!pathname.match(regexp)),
  );

  useEffect(() => {
    setPathAllowed(!regexpUrlsAuth.some((regexp) => !!pathname.match(regexp)));
  }, [pathname]);

  useEffect(() => {
    if (!hasTracked && user && authStates.isSuccess) {
      trackEvent({
        eventName: 'user',
        id: user?.id || '',
        email: user?.email || '',
      });
      setHasTracked(true);
    }
  }, [hasTracked, authStates.isSuccess, user, trackEvent]);

  return {
    user,
    authenticated: !!user && authStates.isSuccess,
    pathAllowed,
    ...authStates,
  };
};
