import { TFunction } from 'i18next';

import { APIError, formatRetryDelay, isRateLimitError } from '@/api';

// Stands in for i18next: returns the key with its interpolations applied, so
// the assertions read as the sentence a user would see.
const t = ((key: string, options?: Record<string, unknown>) =>
  Object.entries(options ?? {}).reduce(
    (text, [name, value]) => text.replace(`{{${name}}}`, String(value)),
    key,
  )) as unknown as TFunction;

describe('rateLimit', () => {
  describe('isRateLimitError', () => {
    it('recognises a throttled response', () => {
      expect(isRateLimitError(new APIError('nope', { status: 429 }))).toBe(
        true,
      );
    });

    it('ignores other failures', () => {
      expect(isRateLimitError(new APIError('nope', { status: 400 }))).toBe(
        false,
      );
      expect(isRateLimitError(new Error('boom'))).toBe(false);
      expect(isRateLimitError(undefined)).toBe(false);
    });
  });

  describe('formatRetryDelay', () => {
    it('rounds up to the coarsest truthful unit', () => {
      expect(formatRetryDelay(30, t)).toBe('about a minute');
      expect(formatRetryDelay(150, t)).toBe('3 minutes');
      expect(formatRetryDelay(3218, t)).toBe('54 minutes');
      expect(formatRetryDelay(3600, t)).toBe('about an hour');
      expect(formatRetryDelay(7200, t)).toBe('2 hours');
    });

    it('never interpolates a value that would need a singular form', () => {
      // Anything under 90s takes the wordy branch, so the smallest number the
      // minutes branch can print is 2.
      expect(formatRetryDelay(89, t)).toBe('about a minute');
      expect(formatRetryDelay(91, t)).toBe('2 minutes');
    });

    it('returns null without a usable delay', () => {
      expect(formatRetryDelay(undefined, t)).toBeNull();
      expect(formatRetryDelay(0, t)).toBeNull();
    });
  });
});
