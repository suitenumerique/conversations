import { TFunction } from 'i18next';

import { RagErrorKind } from './ragErrorKinds';

export { STATUS_LINK_KINDS } from './ragErrorKinds';

// concurrent_reindex is not handled here: conversation_reindexer.py aborts the
// stream with FinishMessagePart(ERROR) before this modal can render.
export const getReindexErrorMessage = (
  t: TFunction,
  kind: string | undefined,
): string => {
  const messages: Record<RagErrorKind, string> = {
    rag_busy: t(
      "Couldn't restore this conversation's documents — the document service is overloaded. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again in a few minutes.",
    ),
    rag_rate_limited: t(
      "Couldn't restore this conversation's documents — the document service rate-limited the request. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again in a few minutes.",
    ),
    rag_unavailable: t(
      "Couldn't restore this conversation's documents — document processing is temporarily unavailable. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again later.",
    ),
    rag_connection_error: t(
      "Couldn't reach the document service to restore this conversation's documents. The assistant will keep going without them, so it may not be able to answer questions about those files. Please try again later.",
    ),
    rag_internal_error: t(
      "Couldn't restore this conversation's documents because of an internal error. Our team has been alerted. The assistant will keep going without them, so it may not be able to answer questions about those files.",
    ),
    rag_error: t(
      "Couldn't restore this conversation's documents. The assistant will keep going without them, so it may not be able to answer questions about those files.",
    ),
  };
  return messages[kind as RagErrorKind] ?? messages.rag_error;
};
