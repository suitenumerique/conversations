"""Unit tests for chat.clients.error_classification."""

import httpx
import pytest
import requests

from chat.clients.error_classification import (
    resolve_llm_error_code,
    resolve_rag_error_code,
)


def _http_error(status_code: int) -> requests.HTTPError:
    """Build a requests.HTTPError whose response carries the given status code."""
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


@pytest.mark.parametrize(
    "status_code, expected",
    [
        (429, "model_rate_limited"),
        (503, "model_busy"),
        (404, "model_not_found"),
        (422, "model_wrong_type"),
        (500, "model_unavailable"),
        (502, "model_unavailable"),
        (504, "model_unavailable"),
        (400, None),
        (403, None),
        (200, None),
        (None, None),
    ],
)
def test_resolve_llm_error_code(status_code, expected):
    """Every documented LLM-side mapping resolves to the expected code."""
    assert resolve_llm_error_code(status_code) == expected


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_http_error(503), "rag_busy"),
        (_http_error(429), "rag_rate_limited"),
        (_http_error(500), "rag_unavailable"),
        (_http_error(502), "rag_unavailable"),
        (_http_error(504), "rag_unavailable"),
        (_http_error(404), "rag_internal_error"),
        (_http_error(403), "rag_internal_error"),
        (_http_error(422), "rag_internal_error"),
        (requests.ConnectionError("boom"), "rag_connection_error"),
        (requests.Timeout("boom"), "rag_connection_error"),
        (httpx.ConnectError("boom"), "rag_connection_error"),
        (httpx.ReadTimeout("boom"), "rag_connection_error"),
        (ValueError("local parse failed"), "rag_error"),
    ],
)
def test_resolve_rag_error_code(exc, expected):
    """Every classified branch returns the expected RAG error code."""
    assert resolve_rag_error_code(exc) == expected
