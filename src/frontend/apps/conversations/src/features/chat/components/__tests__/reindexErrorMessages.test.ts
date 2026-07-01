import { TFunction } from 'i18next';

import {
  STATUS_LINK_KINDS,
  getReindexErrorMessage,
} from '../reindexErrorMessages';

const t = ((key: string) => key) as unknown as TFunction;

describe('getReindexErrorMessage', () => {
  it.each([
    [
      'rag_busy',
      "Couldn't restore this conversation's documents — the document service is overloaded. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again in a few minutes.",
    ],
    [
      'rag_rate_limited',
      "Couldn't restore this conversation's documents — the document service rate-limited the request. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again in a few minutes.",
    ],
    [
      'rag_unavailable',
      "Couldn't restore this conversation's documents — document processing is temporarily unavailable. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again later.",
    ],
    [
      'rag_connection_error',
      "Couldn't reach the document service to restore this conversation's documents. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again later.",
    ],
    [
      'rag_internal_error',
      "Couldn't restore this conversation's documents because of an internal error. Our team has been alerted. The assistant will keep going without them, so it may not be able to answer questions about those files.",
    ],
    [
      'rag_error',
      "Couldn't restore this conversation's documents. The assistant will keep going without them, so it may not be able to answer questions about those files.",
    ],
  ])('returns the matching message for %s', (kind, expected) => {
    expect(getReindexErrorMessage(t, kind)).toBe(expected);
  });

  it('falls back to the generic rag_error message when kind is missing', () => {
    expect(getReindexErrorMessage(t, undefined)).toBe(
      "Couldn't restore this conversation's documents. The assistant will keep going without them, so it may not be able to answer questions about those files.",
    );
  });

  it('falls back to the generic rag_error message when kind is unknown', () => {
    expect(getReindexErrorMessage(t, 'rag_meow')).toBe(
      "Couldn't restore this conversation's documents. The assistant will keep going without them, so it may not be able to answer questions about those files.",
    );
  });
});

describe('STATUS_LINK_KINDS', () => {
  it.each([
    'rag_unavailable',
    'rag_busy',
    'rag_rate_limited',
    'rag_connection_error',
  ])('includes %s', (kind) => {
    expect(STATUS_LINK_KINDS.has(kind)).toBe(true);
  });

  it.each(['rag_internal_error', 'rag_error', 'concurrent_reindex'])(
    'does not include %s',
    (kind) => {
      expect(STATUS_LINK_KINDS.has(kind)).toBe(false);
    },
  );
});
