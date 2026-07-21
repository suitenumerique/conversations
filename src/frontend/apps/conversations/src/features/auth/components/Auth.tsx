import { PropsWithChildren } from 'react';
import { Navigate, useLocation } from 'react-router';

import { Box, Loader } from '@/components';
import { useConfig } from '@/core';

import { useActivationStatus } from '../api/useActivationStatus';
import { HOME_URL } from '../conf';
import { useAuth } from '../hooks';
import { attemptSilentLogin, canAttemptSilentLogin } from '../silentLogin';
import { getAuthUrl, gotoLogin } from '../utils';

export const Auth = ({ children }: PropsWithChildren) => {
  const { isLoading, pathAllowed, isFetchedAfterMount, authenticated } =
    useAuth();
  const location = useLocation();
  // URLs may carry a trailing slash (the previous static export produced them),
  // so normalise before comparing against the route paths below.
  const pathname = location.pathname.replace(/(.)\/$/, '$1');
  const { data: config, isLoading: isConfigLoading } = useConfig();
  const { data: activationStatus, isLoading: isActivationLoading } =
    useActivationStatus();

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
  if (pathname === HOME_URL && authenticated) {
    return <Navigate to="/" replace />;
  }

  /**
   * Activation check: If user is authenticated, config requires activation, and user is not activated,
   * redirect to activation page (unless already on activation page).
   */
  if (
    authenticated &&
    config?.ACTIVATION_REQUIRED &&
    pathname !== '/activation'
  ) {
    // Show loading while checking activation status
    if (isActivationLoading) {
      return (
        <Box $height="100vh" $width="100vw" $align="center" $justify="center">
          <Loader />
        </Box>
      );
    }

    // If activation is required but user is not activated, redirect to activation page
    if (activationStatus && !activationStatus.is_activated) {
      return <Navigate to="/activation" replace />;
    }
  }

  return children;
};
