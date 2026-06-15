# Error Handling

When an upstream provider fails, the backend classifies the failure and emits a typed error code in the Vercel AI SDK stream. The frontend reads this code and displays a specific message — with an optional link to the status page for operational outages.

## LLM Provider Errors

When the LLM provider fails, the backend emits a typed error code in the Vercel AI SDK stream. The frontend reads this code and displays a specific message.

### Error mapping

| Provider failure | pydantic-ai exception | Error code | User-facing message |
|---|---|---|---|
| HTTP 5xx except 503 (500, 502, 504…) | `ModelHTTPError` (`status_code >= 500`) | `model_unavailable` | "The AI inference provider is temporarily unavailable. Please try again later." |
| HTTP 503 (service busy) | `ModelHTTPError` (`status_code == 503`) | `model_busy` | "The AI inference provider is too busy. Please try again later." |
| HTTP 429 (rate limit) | `ModelHTTPError` (`status_code == 429`) | `model_rate_limited` | "The AI inference provider is overloaded. Please try again in a few minutes." |
| HTTP 404 (not found) | `ModelHTTPError` (`status_code == 404`) | `model_not_found` | "We encountered an internal error. Our team has been alerted. Please try again later." |
| HTTP 422 (validation error) | `HTTPValidationError` (`status_code == 422`) | `model_wrong_type` | "We encountered an internal error. Our team has been alerted. Please try again later." |
| No TCP connection, DNS failure, timeout | `ModelAPIError` | `model_connection_error` | "Unable to reach the AI inference provider. Please try again later." |
| Any other error | uncaught → generic Vercel AI SDK error | `generic` | "Sorry, an error occurred. Please try again." |

## RAG / Document Parsing Errors

When the document parsing/RAG pipeline fails (Albert's `/v1/parse-beta`, `/v1/collections`, `/v1/documents`, or local parsers), the backend classifies the failure and emits a typed error kind on the `document_parsing` tool result. The frontend reads this kind and displays a specific message.

### Error mapping

| Failure | Error kind | Status link | User-facing message |
|---|---|---|---|
| HTTP 503 (service busy) | `rag_busy` | yes | "The document service is too busy. Please try again later." |
| HTTP 429 (rate limited) | `rag_rate_limited` | yes | "Too many document requests. Please try again in a few minutes." |
| HTTP ≥500 except 503 | `rag_unavailable` | yes | "Document processing is temporarily unavailable. Please try again later." |
| Any other 4xx (auth, quota, validation, payload too large…) | `rag_internal_error` | no | "We encountered an internal error. Our team has been alerted." |
| Connection error / timeout (no response) | `rag_connection_error` | yes | "Unable to reach the document service. Please try again later." |
| Other (non-HTTP local failure, missing document id, ODT/markitdown parser…) | `rag_error` | no | "Your document could not be processed. Please try again." |
| Concurrent re-index of the conversation collection | `concurrent_reindex` | no | "Documents are currently being re-indexed. Please retry in a moment." |

### Conversation re-index errors

The same `rag_*` kinds flow through the `conversation_resume` tool result emitted by `chat/clients/conversation_reindexer.py` when a previously de-indexed conversation is resumed and the Albert backend fails. The frontend renders a kind-aware message in the "Re-indexing Error" modal via `reindexErrorMessages.ts`. The wording differs from the `document_parsing` strings: it names the consequence ("the assistant will keep going without the documents, so it may not be able to answer questions about those files") since the user just clicked into the conversation and is about to send a message — the loss of context is what matters more than the technical cause. The status-link policy is identical to the document-parsing case.

## Status page link

Set `STATUS_PAGE_URL` to display a "Check service status" link alongside operational availability errors (LLM: `model_unavailable`, `model_busy`, `model_rate_limited`, `model_connection_error`; RAG: `rag_unavailable`, `rag_busy`, `rag_rate_limited`, `rag_connection_error`). Configuration / internal errors (`model_not_found`, `model_wrong_type`, `rag_internal_error`, `rag_error`, `concurrent_reindex`) show a generic message and do not display a status link.

```bash
STATUS_PAGE_URL=https://albert.sites.beta.gouv.fr/about/status/
```

The link is omitted when the variable is unset.

## Implementation

- **Backend (LLM):** `src/backend/chat/clients/pydantic_ai.py` — `_stream_content` catches provider exceptions and emits `ErrorPart` events.
- **Classifiers (shared):** `src/backend/chat/clients/error_classification.py` — `resolve_llm_error_code` (LLM) and `resolve_rag_error_code` (RAG); both pipelines import from here.
- **Backend (RAG upload):** `src/backend/chat/clients/pydantic_ai.py` — `_handle_input_documents` calls `resolve_rag_error_code` and emits a typed kind on the `document_parsing` `ToolResultPart`. All failures log at `logger.exception` so Sentry catches outages.
- **Backend (RAG re-index):** `src/backend/chat/clients/conversation_reindexer.py` — same classifier; emits the kind on the `conversation_resume` `ToolResultPart` for both the "collection create failed" and "all documents failed" branches.
- **Frontend (LLM):** `src/frontend/apps/conversations/src/features/chat/components/ChatError.tsx` — renders the message based on `errorType` prop.
- **Frontend (RAG upload):** `src/frontend/apps/conversations/src/features/chat/components/ToolInvocationItem.tsx` — renders inline via `documentParsingErrorMessages.ts`. Shared `STATUS_LINK_KINDS` lives in `ragErrorKinds.ts`.
- **Frontend (RAG re-index):** `src/frontend/apps/conversations/src/features/chat/components/Chat.tsx` — renders the "Re-indexing Error" modal via `reindexErrorMessages.ts`.
- **Config:** `src/backend/conversations/settings.py` and `src/backend/core/api/viewsets.py` — `STATUS_PAGE_URL` is exposed via the `config/` API.
