"""Map upstream exceptions to typed error codes for the chat stream.

Two classifiers live here:

- ``resolve_llm_error_code`` for LLM-provider failures, called from the
  ``_stream_content`` exception handler in ``pydantic_ai.AIAgentService``.
- ``resolve_rag_error_code`` for document-parsing / re-index failures, called
  from ``_handle_input_documents`` and ``reindex_conversation``.

Keeping both in one module avoids drift between the two pipelines and gives the
test suite a single place to lock down the status-code → kind mapping.
"""

import httpx
import requests

# LLM-side error codes (also used by the frontend ChatErrorType union).
MODEL_RATE_LIMITED = "model_rate_limited"
MODEL_BUSY = "model_busy"
MODEL_NOT_FOUND = "model_not_found"
MODEL_WRONG_TYPE = "model_wrong_type"
MODEL_UNAVAILABLE = "model_unavailable"

# RAG-side error codes (also used by the frontend RagErrorKind union).
RAG_BUSY = "rag_busy"
RAG_RATE_LIMITED = "rag_rate_limited"
RAG_UNAVAILABLE = "rag_unavailable"
RAG_INTERNAL_ERROR = "rag_internal_error"
RAG_CONNECTION_ERROR = "rag_connection_error"
RAG_ERROR = "rag_error"

LLM_STATUS_TO_ERROR_CODE = {
    429: MODEL_RATE_LIMITED,
    503: MODEL_BUSY,
    404: MODEL_NOT_FOUND,
    422: MODEL_WRONG_TYPE,
}

# LLM-side: expected operational errors that should not trigger ERROR-level logging
# or Sentry alerts (the connection-error path logs at warning separately).
EXPECTED_LLM_STATUS_CODES = {429, 503}

RAG_STATUS_TO_ERROR_CODE = {
    503: RAG_BUSY,
    429: RAG_RATE_LIMITED,
}


def resolve_llm_error_code(status_code: int | None) -> str | None:
    """Map an LLM provider HTTP status code to an error code, or None to re-raise."""
    if status_code is None:
        return None
    if status_code in LLM_STATUS_TO_ERROR_CODE:
        return LLM_STATUS_TO_ERROR_CODE[status_code]
    if status_code >= 500:
        return MODEL_UNAVAILABLE
    return None


def resolve_rag_error_code(exc: Exception) -> str:
    """Map a RAG pipeline exception to a typed error code for the frontend.

    Handles both ``requests`` (sync Albert calls) and ``httpx`` (async Albert
    calls) exception hierarchies, plus the local-parser / missing-id paths that
    raise non-HTTP exceptions.
    """
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is None:
        if isinstance(exc, (requests.ConnectionError, requests.Timeout, httpx.RequestError)):
            return RAG_CONNECTION_ERROR
        return RAG_ERROR
    if status_code in RAG_STATUS_TO_ERROR_CODE:
        return RAG_STATUS_TO_ERROR_CODE[status_code]
    if status_code >= 500:
        return RAG_UNAVAILABLE
    return RAG_INTERNAL_ERROR
