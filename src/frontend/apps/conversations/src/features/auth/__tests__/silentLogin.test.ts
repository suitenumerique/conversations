import { navigate } from '@/utils/system';

import { attemptSilentLogin, canAttemptSilentLogin } from '../silentLogin';

vi.mock('@/utils/system', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/system')>()),
  navigate: vi.fn(),
}));

const mockNavigate = vi.mocked(navigate);

const SILENT_LOGIN_RETRY_KEY = 'silent-login-retry';

describe('silentLogin', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
    mockNavigate.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('canAttemptSilentLogin', () => {
    it('returns true when no prior attempt', () => {
      expect(canAttemptSilentLogin()).toBe(true);
    });

    it('returns false within the retry interval', () => {
      vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);

      vi.setSystemTime(new Date('2026-01-01T00:00:15Z'));
      expect(canAttemptSilentLogin()).toBe(false);
    });

    it('returns true after the retry interval expires', () => {
      vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);

      vi.setSystemTime(new Date('2026-01-01T00:00:31Z'));
      expect(canAttemptSilentLogin()).toBe(true);
    });
  });

  describe('attemptSilentLogin', () => {
    it('sets the retry throttle in localStorage', () => {
      vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);

      const stored = localStorage.getItem(SILENT_LOGIN_RETRY_KEY);
      expect(stored).toBe(
        String(new Date('2026-01-01T00:00:00Z').getTime() + 30000),
      );
    });

    it('redirects to the silent auth URL', () => {
      attemptSilentLogin(30);
      expect(mockNavigate).toHaveBeenCalledTimes(1);
      const target = mockNavigate.mock.calls[0][0];
      expect(target).toContain('authenticate');
      expect(target).toContain('silent=true');
    });

    it('does nothing if retry is not allowed', () => {
      vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
      attemptSilentLogin(30);
      mockNavigate.mockClear();

      vi.setSystemTime(new Date('2026-01-01T00:00:10Z'));
      attemptSilentLogin(30);

      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });
});
