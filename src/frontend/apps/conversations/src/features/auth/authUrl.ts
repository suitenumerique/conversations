import { LOGIN_URL } from './conf';

export const authUrl = ({ silent = false } = {}) => {
  const url = new URL(LOGIN_URL);
  if (silent) {
    url.searchParams.set('silent', 'true');
  }
  return url;
};
