import { TFunction } from 'i18next';

import { APIError } from './APIError';

/**
 * Type guard for a response rejected by a server-side rate limit.
 */
export const isRateLimitError = (error: unknown): error is APIError =>
  error instanceof APIError && error.status === 429;

/**
 * Human-readable delay before a rate limited action can be retried.
 *
 * Rounds up to the coarsest unit that stays truthful, since the exact second
 * is never actionable: someone told to wait 3218 seconds only needs to know
 * it is about 54 minutes. Returns null when the server sent no usable delay.
 */
export const formatRetryDelay = (
  seconds: number | undefined,
  t: TFunction,
): string | null => {
  if (!seconds || seconds <= 0) {
    return null;
  }
  // Phrased so that every interpolated value is plural, which keeps these as
  // ordinary strings: the codebase has no plural-form translation keys.
  if (seconds < 90) {
    return t('about a minute');
  }
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) {
    return t('{{minutes}} minutes', { minutes });
  }
  const hours = Math.ceil(minutes / 60);
  return hours === 1 ? t('about an hour') : t('{{hours}} hours', { hours });
};

/**
 * Message shown when the user hits a creation rate limit.
 *
 * The API answers with the framework default wording, which talks about
 * requests being throttled and counts in raw seconds; this states what
 * happened in product terms instead, and adds the delay when we know it.
 */
export const rateLimitMessage = (error: APIError, t: TFunction): string => {
  const delay = formatRetryDelay(error.retryAfter, t);
  return delay
    ? t('You have made too many requests. Please try again in {{delay}}.', {
        delay,
      })
    : t('You have made too many requests. Please try again later.');
};
