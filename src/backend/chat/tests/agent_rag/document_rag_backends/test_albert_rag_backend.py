"""
HTTP-level tests for AlbertRagBackend.search / asearch.

Mocks the Albert API at the wire level (responses for requests, respx for httpx)
and exercises the real backend class. Verifies:

- Correct payload construction (with/without document_name filter)
- Empty filtered results return empty RAGWebResults (no recursive retry)
  -> regression test for the silent-fallback removal
- Non-empty results map to the right RAGWebResult shape and propagate usage
"""

import json

import pytest
import responses
import respx
from httpx import Response

from chat.agent_rag.document_rag_backends.albert_rag_backend import AlbertRagBackend

ALBERT_BASE_URL = "https://albert.test"
SEARCH_URL = f"{ALBERT_BASE_URL}/v1/search"


@pytest.fixture(name="albert_backend")
def albert_backend_fixture(settings):
    """A backend pointing at a test API and a fixed collection."""
    settings.ALBERT_API_URL = ALBERT_BASE_URL
    settings.ALBERT_API_KEY = "test-key"
    return AlbertRagBackend(collection_id="123")


def _empty_albert_response():
    return {"data": [], "usage": {"prompt_tokens": 1, "completion_tokens": 0}}


def _one_result_albert_response():
    return {
        "data": [
            {
                "method": "semantic",
                "chunk": {
                    "id": 1,
                    "content": "snippet from doc",
                    "metadata": {"document_name": "report.pdf"},
                },
                "score": 0.9,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


# Sync search


@responses.activate
def test_search_without_filter_does_not_send_metadata_filters(albert_backend):
    """No document_name -> request body has no metadata_filters key."""
    responses.post(
        url=SEARCH_URL,
        json=_one_result_albert_response(),
        status=200,
    )

    albert_backend.search("any query")

    assert len(responses.calls) == 1
    payload = json.loads(responses.calls[0].request.body)
    assert "metadata_filters" not in payload
    assert payload["prompt"] == "any query"
    assert payload["collections"] == [123]


@responses.activate
def test_search_with_filter_sends_metadata_filters(albert_backend):
    """document_name -> request body carries the metadata_filters dict."""
    responses.post(
        url=SEARCH_URL,
        json=_one_result_albert_response(),
        status=200,
    )

    albert_backend.search("any query", document_name="report.pdf")

    payload = json.loads(responses.calls[0].request.body)
    assert payload["metadata_filters"] == {
        "key": "document_name",
        "value": "report.pdf",
        "type": "eq",
    }


@responses.activate
def test_search_with_filter_empty_returns_empty_no_recursion(albert_backend, caplog):
    """
    Filtered search returning empty must NOT recurse into an unfiltered call.
    Regression test for the silent-fallback removal.
    """
    responses.post(
        url=SEARCH_URL,
        json=_empty_albert_response(),
        status=200,
    )

    with caplog.at_level("INFO", logger="chat.agent_rag.document_rag_backends.albert_rag_backend"):
        results = albert_backend.search("any query", document_name="missing.pdf")

    assert results.data == []
    # Exactly one HTTP call: no recursive unfiltered retry.
    assert len(responses.calls) == 1
    # And the empty-with-filter case is announced at info level.
    assert any("returned no results" in r.message for r in caplog.records)


@responses.activate
def test_search_without_filter_empty_returns_empty(albert_backend, caplog):
    """Unfiltered empty result returns empty RAGWebResults; no info log."""
    responses.post(
        url=SEARCH_URL,
        json=_empty_albert_response(),
        status=200,
    )

    with caplog.at_level("INFO", logger="chat.agent_rag.document_rag_backends.albert_rag_backend"):
        results = albert_backend.search("any query")

    assert results.data == []
    assert len(responses.calls) == 1
    # The "returned no results" info log is only for filtered searches.
    assert not any("returned no results" in r.message for r in caplog.records)


@responses.activate
def test_search_returns_results_with_usage(albert_backend):
    """A successful search maps Albert chunks to RAGWebResult and propagates usage."""
    responses.post(
        url=SEARCH_URL,
        json=_one_result_albert_response(),
        status=200,
    )

    results = albert_backend.search("any query")

    assert len(results.data) == 1
    assert results.data[0].url == "report.pdf"
    assert results.data[0].content == "snippet from doc"
    assert results.data[0].score == pytest.approx(0.9)
    assert results.usage.prompt_tokens == 10
    assert results.usage.completion_tokens == 20


# Async search


@pytest.mark.asyncio
@respx.mock
async def test_asearch_with_filter_empty_returns_empty_no_recursion(albert_backend, caplog):
    """Same regression check as the sync variant, on the async path."""
    route = respx.post(SEARCH_URL).mock(return_value=Response(200, json=_empty_albert_response()))

    with caplog.at_level("INFO", logger="chat.agent_rag.document_rag_backends.albert_rag_backend"):
        results = await albert_backend.asearch("any query", document_name="missing.pdf")

    assert results.data == []
    assert route.call_count == 1  # no recursive retry
    assert any("returned no results" in r.message for r in caplog.records)


@pytest.mark.asyncio
@respx.mock
async def test_asearch_with_filter_sends_metadata_filters(albert_backend):
    """Async path: metadata_filters present when document_name given."""
    route = respx.post(SEARCH_URL).mock(
        return_value=Response(200, json=_one_result_albert_response())
    )

    await albert_backend.asearch("any query", document_name="report.pdf")

    payload = json.loads(route.calls[0].request.content)
    assert payload["metadata_filters"] == {
        "key": "document_name",
        "value": "report.pdf",
        "type": "eq",
    }


@pytest.mark.asyncio
@respx.mock
async def test_asearch_returns_results_with_usage(albert_backend):
    """Async path: results map and usage propagates."""
    respx.post(SEARCH_URL).mock(return_value=Response(200, json=_one_result_albert_response()))

    results = await albert_backend.asearch("any query")

    assert len(results.data) == 1
    assert results.data[0].url == "report.pdf"
    assert results.usage.prompt_tokens == 10
