import { authUrl } from './authUrl';

// Stores the earliest timestamp (ms) at which a new silent login attempt is allowed.
// Prevents infinite redirect loops when the identity provider (proconnect/keycloak)
// has no active session:
// silent login fails -> app reloads -> without throttle, would retry immediately -> loop.
const SILENT_LOGIN_RETRY_KEY = 'silent-login-retry';

const isRetryAllowed = () => {
  const raw = localStorage.getItem(SILENT_LOGIN_RETRY_KEY);
  if (!raw) {
    return true;
  }
  const nextAllowedTime = Number(raw);
  if (!Number.isFinite(nextAllowedTime)) {
    localStorage.removeItem(SILENT_LOGIN_RETRY_KEY);
    return true;
  }
  return new Date().getTime() >= nextAllowedTime;
};

const setNextRetryTime = (retryIntervalInSeconds: number) => {
  const nextRetryTime = new Date().getTime() + retryIntervalInSeconds * 1000;
  localStorage.setItem(SILENT_LOGIN_RETRY_KEY, String(nextRetryTime));
};

const initiateSilentLogin = () => {
  window.location.href = authUrl({ silent: true }).href;
};

export const canAttemptSilentLogin = () => {
  return isRetryAllowed();
};

export const attemptSilentLogin = (retryIntervalInSeconds: number) => {
  if (!isRetryAllowed()) {
    return;
  }
  setNextRetryTime(retryIntervalInSeconds);
  initiateSilentLogin();
};
