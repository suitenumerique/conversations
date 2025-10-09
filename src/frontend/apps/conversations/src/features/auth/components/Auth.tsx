import { useRouter } from 'next/router';
import { PropsWithChildren } from 'react';

import { Box, Loader } from '@/components';
import { useConfig } from '@/core';

import { useActivationStatus } from '../api/useActivationStatus';
import { HOME_URL } from '../conf';
import { useAuth } from '../hooks';
import { getAuthUrl, gotoLogin } from '../utils';

export const Auth = ({ children }: PropsWithChildren) => {
  const { isLoading, pathAllowed, isFetchedAfterMount, authenticated } =
    useAuth();
  const { replace, pathname } = useRouter();
  const { data: config } = useConfig();
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
      void replace(authUrl);
      return (
        <Box $height="100vh" $width="100vw" $align="center" $justify="center">
          <Loader />
        </Box>
      );
    }
  }

  /**
   * If the user is not authenticated and the path is not allowed, we redirect to the login page.
   */
  if (!authenticated && !pathAllowed) {
    if (config?.FRONTEND_HOMEPAGE_FEATURE_ENABLED) {
      void replace(HOME_URL);
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
    void replace('/');
    return (
      <Box $height="100vh" $width="100vw" $align="center" $justify="center">
        <Loader />
      </Box>
    );
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
      void replace('/activation');
      return (
        <Box $height="100vh" $width="100vw" $align="center" $justify="center">
          <Loader />
        </Box>
      );
    }
  }

  return children;
};
