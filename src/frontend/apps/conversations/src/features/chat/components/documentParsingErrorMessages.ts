import { TFunction } from 'i18next';

import { RagErrorKind } from './ragErrorKinds';

export { STATUS_LINK_KINDS } from './ragErrorKinds';

export type DocumentParsingErrorKind = 'concurrent_reindex' | RagErrorKind;

export const getDocumentParsingErrorMessage = (
  t: TFunction,
  kind: string | undefined,
): string => {
  const messages: Record<DocumentParsingErrorKind, string> = {
    concurrent_reindex: t(
      'Documents are currently being re-indexed. Please retry in a moment.',
    ),
    rag_busy: t('The document service is too busy. Please try again later.'),
    rag_rate_limited: t(
      'Too many document requests. Please try again in a few minutes.',
    ),
    rag_unavailable: t(
      'Document processing is temporarily unavailable. Please try again later.',
    ),
    rag_internal_error: t(
      'We encountered an internal error. Our team has been alerted.',
    ),
    rag_connection_error: t(
      'Unable to reach the document service. Please try again later.',
    ),
    rag_error: t('Your document could not be processed. Please try again.'),
  };
  return messages[kind as DocumentParsingErrorKind] ?? messages.rag_error;
};
