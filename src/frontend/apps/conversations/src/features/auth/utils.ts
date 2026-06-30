import { User } from './api/types';
import { LOGIN_URL, LOGOUT_URL, PATH_AUTH_LOCAL_STORAGE } from './conf';

/** Safe email for display, since the API may return a null email. */
export const getUserEmail = (user: User) => user.email ?? '';

/** Best available display name, falling back through email/short name to a default. */
export const getUserFullName = (user: User, fallback: string) =>
  user.full_name || user.email || user.short_name || fallback;

export const getAuthUrl = () => {
  const path_auth = localStorage.getItem(PATH_AUTH_LOCAL_STORAGE);
  if (path_auth) {
    localStorage.removeItem(PATH_AUTH_LOCAL_STORAGE);
    return path_auth;
  }
};

export const setAuthUrl = () => {
  if (window.location.pathname !== '/') {
    localStorage.setItem(PATH_AUTH_LOCAL_STORAGE, window.location.pathname);
  }
};

export const gotoLogin = (withRedirect = true) => {
  if (withRedirect) {
    setAuthUrl();
  }

  window.location.replace(LOGIN_URL);
};

export const gotoLogout = () => {
  window.location.replace(LOGOUT_URL);
};
