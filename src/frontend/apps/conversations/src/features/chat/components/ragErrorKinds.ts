export type RagErrorKind =
  | 'rag_busy'
  | 'rag_rate_limited'
  | 'rag_unavailable'
  | 'rag_internal_error'
  | 'rag_connection_error'
  | 'rag_error';

export const STATUS_LINK_KINDS: ReadonlySet<string> = new Set([
  'rag_unavailable',
  'rag_busy',
  'rag_rate_limited',
  'rag_connection_error',
]);
