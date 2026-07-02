import { TFunction } from 'i18next';

import { ChatErrorType } from './ChatError';

export const getChatErrorMessage = (
  t: TFunction,
  errorType: ChatErrorType,
): string => {
  const messages: Record<ChatErrorType, string> = {
    generic: t('Sorry, an error occurred. Please try again.'),
    model_unavailable: t(
      'The AI inference provider is temporarily unavailable. Please try again later.',
    ),
    model_rate_limited: t(
      'The AI inference provider is overloaded. Please try again in a few minutes.',
    ),
    model_connection_error: t(
      'Unable to reach the AI inference provider. Please try again later.',
    ),
    model_not_found: t(
      'We encountered an internal error. Our team has been alerted. Please try again later.',
    ),
    model_wrong_type: t(
      'We encountered an internal error. Our team has been alerted. Please try again later.',
    ),
    model_busy: t(
      'The AI inference provider is too busy. Please try again later.',
    ),
  };
  return messages[errorType];
};
