import { attemptSilentLogin, canAttemptSilentLogin } from '../silentLogin';

const SILENT_LOGIN_RETRY_KEY = 'silent-login-retry';

describe('silentLogin', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.useFakeTimers();
    Object.defineProperty(window, 'location', {
      value: { ...window.location, href: '' },
      writable: true,
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('canAttemptSilentLogin', () => {
    it('returns true when no prior attempt', () => {
      expect(canAttemptSilentLogin()).toBe(true);
    });

    it('returns false within the retry interval', () => {
      jest.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);

      jest.setSystemTime(new Date('2026-01-01T00:00:15Z'));
      expect(canAttemptSilentLogin()).toBe(false);
    });

    it('returns true after the retry interval expires', () => {
      jest.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);

      jest.setSystemTime(new Date('2026-01-01T00:00:31Z'));
      expect(canAttemptSilentLogin()).toBe(true);
    });
  });

  describe('attemptSilentLogin', () => {
    it('sets the retry throttle in localStorage', () => {
      jest.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);

      const stored = localStorage.getItem(SILENT_LOGIN_RETRY_KEY);
      expect(stored).toBe(
        String(new Date('2026-01-01T00:00:00Z').getTime() + 30000),
      );
    });

    it('redirects to the silent auth URL', () => {
      attemptSilentLogin(30);
      expect(window.location.href).toContain('authenticate');
      expect(window.location.href).toContain('silent=true');
    });

    it('does nothing if retry is not allowed', () => {
      jest.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);
      window.location.href = '';

      jest.setSystemTime(new Date('2026-01-01T00:00:10Z'));
      attemptSilentLogin(30);

      expect(window.location.href).toBe('');
    });
  });
});
