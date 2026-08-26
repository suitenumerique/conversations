import { PropsWithChildren } from 'react';
import { Navigate, useLocation } from 'react-router';

import { Box, Loader } from '@/components';
import { useConfig } from '@/core';

import { HOME_URL } from '../conf';
import { useAuth } from '../hooks';
import { attemptSilentLogin, canAttemptSilentLogin } from '../silentLogin';
import { getAuthUrl, gotoLogin } from '../utils';

export const Auth = ({ children }: PropsWithChildren) => {
  const { isLoading, pathAllowed, isFetchedAfterMount, authenticated } =
    useAuth();
  const { pathname } = useLocation();
  // The router reports the real URL, which may carry the trailing slash the
  // Next export used to add; the comparisons below are exact.
  const path = pathname.replace(/\/+$/, '') || '/';
  const { data: config, isLoading: isConfigLoading } = useConfig();

  if (isLoading && !isFetchedAfterMount) {
    return (
      <Box $height="100vh" $width="100vw" $align="center" $justify="center">
        <Loader />
      </Box>
    );
  }

  /**
   * If the user is authenticated and wanted initially to access a document,
   * we redirect to the document page.
   */
  if (authenticated) {
    const authUrl = getAuthUrl();
    if (authUrl) {
      return <Navigate to={authUrl} replace />;
    }
  }

  /**
   * If the user is not authenticated and the path is not allowed,
   * try silent login first, then fall back to the login page.
   */
  if (!authenticated && !pathAllowed) {
    if (isConfigLoading) {
      return (
        <Box $height="100vh" $width="100vw" $align="center" $justify="center">
          <Loader />
        </Box>
      );
    }
    if (config?.FRONTEND_SILENT_LOGIN_ENABLED && canAttemptSilentLogin()) {
      attemptSilentLogin(30);
    } else if (config?.FRONTEND_HOMEPAGE_FEATURE_ENABLED) {
      return <Navigate to={HOME_URL} replace />;
    } else {
      gotoLogin();
    }
    return (
      <Box $height="100vh" $width="100vw" $align="center" $justify="center">
        <Loader />
      </Box>
    );
  }

  /**
   * If the user is authenticated and the path is the home page, we redirect to the index.
   */
  if (path === HOME_URL && authenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
};
