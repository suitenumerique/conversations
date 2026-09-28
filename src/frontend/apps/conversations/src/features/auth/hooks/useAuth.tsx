import { useEffect, useState } from 'react';
import { useLocation } from 'react-router';

import { useAnalytics } from '@/libs';

import { useAuthQuery } from '../api';

const regexpUrlsAuth = [
  /\/chat\/$/g, // New conversation requires authentication
  /\/chat$/g,
  /\/chat\/.+$/g, // Conversation requires authentication: remove to allow anonymous access
  /^\/$/g, // Root requires authentication
];

export const useAuth = () => {
  const {
    data: user,
    isFetched,
    isFetchedAfterMount,
    isLoading,
    isSuccess,
  } = useAuthQuery();
  const { pathname } = useLocation();
  const { trackEvent } = useAnalytics();
  const [hasTracked, setHasTracked] = useState(isFetched);
  const [pathAllowed, setPathAllowed] = useState<boolean>(
    !regexpUrlsAuth.some((regexp) => !!pathname.match(regexp)),
  );

  useEffect(() => {
    setPathAllowed(!regexpUrlsAuth.some((regexp) => !!pathname.match(regexp)));
  }, [pathname]);

  useEffect(() => {
    if (!hasTracked && user && isSuccess) {
      trackEvent({
        eventName: 'user',
        id: user?.id || '',
        email: user?.email || '',
        sub: user?.sub,
      });
      setHasTracked(true);
    }
  }, [hasTracked, isSuccess, user, trackEvent]);

  return {
    user,
    authenticated: !!user && isSuccess,
    pathAllowed,
    isLoading,
    isFetchedAfterMount,
  };
};
