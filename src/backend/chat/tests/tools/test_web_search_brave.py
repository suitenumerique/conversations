"""Tests for the Brave web search tool."""

from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from pydantic_ai import RunContext, RunUsage

from chat.tools.web_search_brave import (
    _extract_and_summarize_snippets,
    _fetch_and_extract,
    _fetch_and_store,
    _query_brave_api,
    web_search_brave,
    web_search_brave_with_document_backend,
)

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


@pytest.fixture(autouse=True)
def brave_settings(settings):
    """Define Brave settings for tests."""
    settings.BRAVE_API_KEY = "test_brave_api_key"
    settings.BRAVE_API_TIMEOUT = 5
    settings.BRAVE_SEARCH_COUNTRY = "US"
    settings.BRAVE_SEARCH_LANG = "en"
    settings.BRAVE_MAX_RESULTS = 3
    settings.BRAVE_SEARCH_SAFE_SEARCH = "moderate"
    settings.BRAVE_SEARCH_SPELLCHECK = True
    settings.BRAVE_SEARCH_EXTRA_SNIPPETS = True
    settings.BRAVE_SUMMARIZATION_ENABLED = False
    settings.BRAVE_MAX_WORKERS = 2
    settings.BRAVE_CACHE_TTL = 3600
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )


@responses.activate
def test_agent_web_search_brave_success_with_extra_snippets():
    """Test when the Brave search returns results with extra_snippets."""
    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {
                        "url": "https://example.com/a",
                        "title": "Result A",
                        "extra_snippets": ["Snippet A1", "Snippet A2"],
                    },
                    {
                        "url": "https://example.com/b",
                        "title": "Result B",
                        "extra_snippets": ["Snippet B1"],
                    },
                ]
            }
        },
        status=200,
    )

    with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
        # Fetch should not be called since extra_snippets are provided
        mock_fetch.side_effect = Exception("fetch_url should not be called")
        tool_return = web_search_brave("test query")

    assert hasattr(tool_return, "return_value")
    assert tool_return.return_value == [
        {
            "link": "https://example.com/a",
            "title": "Result A",
            "extra_snippets": ["Snippet A1", "Snippet A2"],
        },
        {
            "link": "https://example.com/b",
            "title": "Result B",
            "extra_snippets": ["Snippet B1"],
        },
    ]
    assert tool_return.metadata["sources"] == {"https://example.com/a", "https://example.com/b"}

    # Check request parameters
    brave_request = responses.calls[0].request
    parsed = urlparse(brave_request.url)
    qs = parse_qs(parsed.query)
    assert qs["q"] == ["test query"]
    assert qs["count"] == ["3"]
    assert qs["search_lang"] == ["en"]
    assert qs["country"] == ["US"]
    assert qs["safesearch"] == ["moderate"]
    assert qs["spellcheck"] == ["True"]
    assert qs["extra_snippets"] == ["True"]
    assert qs["result_filter"] == ["web,faq,query"]


@responses.activate
def test_agent_web_search_brave_success_without_extra_snippets():
    """Test when the Brave search returns results without extra_snippets."""
    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/c", "title": "Result C"},  # pas d'extra_snippets
                ]
            }
        },
        status=200,
    )

    with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
        # Fetch should not be called since extra_snippets are provided
        mock_fetch.return_value = (
            '<html><body>Extracted Content C<a href="url">link</a></body></html>'
        )
        tool_return = web_search_brave("test query")

    assert tool_return.return_value == [
        {
            "link": "https://example.com/c",
            "title": "Result C",
            "extra_snippets": ["Extracted Content C\nlink"],
        }
    ]
    assert tool_return.metadata["sources"] == {"https://example.com/c"}


@responses.activate
def test_agent_web_search_brave_success_without_extra_snippets_summarization(settings):
    """Test when the Brave search returns results without extra_snippets."""
    settings.BRAVE_SUMMARIZATION_ENABLED = True

    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/c", "title": "Result C"},  # pas d'extra_snippets
                ]
            }
        },
        status=200,
    )

    with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
        with patch("chat.tools.web_search_brave.llm_summarize") as mock_llm_summarize:
            # Fetch should not be called since extra_snippets are provided
            mock_fetch.return_value = (
                '<html><body>Extracted Content C<a href="url">link</a></body></html>'
            )
            mock_llm_summarize.return_value = "Summarized extracted Content C\nlink"
            tool_return = web_search_brave("test query")

            mock_llm_summarize.assert_called_with("test query", "Extracted Content C\nlink")

    assert tool_return.return_value == [
        {
            "link": "https://example.com/c",
            "title": "Result C",
            "extra_snippets": ["Summarized extracted Content C\nlink"],
        }
    ]
    assert tool_return.metadata["sources"] == {"https://example.com/c"}


@responses.activate
def test_agent_web_search_brave_empty_results():
    """Test when the Brave search returns no results."""
    responses.add(
        responses.GET,
        BRAVE_URL,
        json={"web": {"results": []}},
        status=200,
    )
    tool_return = web_search_brave("empty query")
    assert tool_return.return_value == []
    assert tool_return.metadata["sources"] == set()


@responses.activate
def test_agent_web_search_brave_http_error():
    """Test handling of HTTP errors from Brave API."""
    responses.add(
        responses.GET,
        BRAVE_URL,
        status=500,
        json={"error": "Internal Server Error"},
    )
    with pytest.raises(Exception) as exc:
        web_search_brave("error query")
    assert "500" in str(exc.value) or "Internal Server Error" in str(exc.value)


@responses.activate
def test_agent_web_search_brave_params_exclude_none(settings):
    """Check that None parameters are excluded from the request."""
    settings.BRAVE_SEARCH_COUNTRY = None
    settings.BRAVE_SEARCH_LANG = None

    responses.add(
        responses.GET,
        BRAVE_URL,
        json={"web": {"results": []}},
        status=200,
    )
    web_search_brave("none params")

    brave_request = responses.calls[0].request
    parsed = urlparse(brave_request.url)
    qs = parse_qs(parsed.query)

    # Mandatory params
    assert qs["q"] == ["none params"]
    assert qs["count"] == ["3"]

    # None params missing
    assert "country" not in qs
    assert "search_lang" not in qs

    # Defined params present
    assert qs["safesearch"] == ["moderate"]
    assert qs["spellcheck"] == ["True"]
    assert qs["extra_snippets"] == ["True"]

    # Empty body for GET request
    assert not brave_request.body


@responses.activate
def test_agent_web_search_brave_parallel_processing(settings):
    """Test parallel processing with multiple workers."""
    settings.BRAVE_MAX_WORKERS = 2

    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/1", "title": "Result 1"},
                    {"url": "https://example.com/2", "title": "Result 2"},
                ]
            }
        },
        status=200,
    )

    with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
        mock_fetch.return_value = "<html><body>Content</body></html>"
        tool_return = web_search_brave("parallel query")

    assert len(tool_return.return_value) == 2
    assert mock_fetch.call_count == 2


@responses.activate
def test_agent_web_search_brave_single_worker(settings):
    """Test processing with single worker (no ThreadPoolExecutor overhead)."""
    settings.BRAVE_MAX_WORKERS = 1

    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/single", "title": "Single Result"},
                ]
            }
        },
        status=200,
    )

    with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
        mock_fetch.return_value = "<html><body>Single Content</body></html>"
        tool_return = web_search_brave("single worker query")

    assert len(tool_return.return_value) == 1
    assert tool_return.return_value[0]["extra_snippets"] == ["Single Content"]


@responses.activate
def test_fetch_and_extract_with_cache():
    """Test caching mechanism in _fetch_and_extract."""
    with patch("chat.tools.web_search_brave.cache") as mock_cache:
        with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
            # First call - cache miss
            mock_cache.get.return_value = None
            mock_fetch.return_value = "<html><body>Cached Content</body></html>"

            result1 = _fetch_and_extract("https://example.com/cache")

            assert result1 == "Cached Content"
            mock_cache.get.assert_called_once()
            mock_cache.set.assert_called_once()

            # Second call - cache hit
            mock_cache.get.return_value = "Cached Content"
            result2 = _fetch_and_extract("https://example.com/cache")

            assert result2 == "Cached Content"
            # fetch_url should still be called only once (from first call)
            assert mock_fetch.call_count == 1


@responses.activate
def test_extract_and_summarize_snippets_empty_document():
    """Test _extract_and_summarize_snippets when extraction returns empty string."""
    with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            mock_fetch.return_value = "<html><body></body></html>"
            mock_extract.return_value = ""

            result = _extract_and_summarize_snippets("query", "https://example.com/empty")

            assert not result


@responses.activate
def test_extract_and_summarize_snippets_summarization_failure(settings):
    """Test _extract_and_summarize_snippets when summarization fails."""
    settings.BRAVE_SUMMARIZATION_ENABLED = True

    with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
        with patch("chat.tools.web_search_brave.llm_summarize") as mock_summarize:
            mock_fetch.return_value = "<html><body>Content</body></html>"
            mock_summarize.side_effect = Exception("Summarization error")

            result = _extract_and_summarize_snippets("query", "https://example.com/error")

            assert not result


@responses.activate
def test_web_search_brave_with_document_backend_success():
    """Test web_search_brave_with_document_backend with successful RAG search."""
    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/doc1", "title": "Document 1"},
                    {"url": "https://example.com/doc2", "title": "Document 2"},
                ]
            }
        },
        status=200,
    )

    mock_ctx = Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)

    mock_document_store = MagicMock()
    mock_rag_result1 = Mock(url="https://example.com/doc1", content="RAG Content 1")
    mock_rag_result2 = Mock(url="https://example.com/doc2", content="RAG Content 2")
    mock_rag_results = Mock(
        data=[mock_rag_result1, mock_rag_result2], usage=Mock(prompt_tokens=10, completion_tokens=5)
    )
    mock_document_store.search.return_value = mock_rag_results

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection.return_value.__enter__.return_value = (
        mock_document_store
    )

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
            mock_fetch.return_value = "<html><body>Document content</body></html>"

            tool_return = web_search_brave_with_document_backend(mock_ctx, "rag query")

    assert len(tool_return.return_value) == 2
    assert tool_return.return_value[0]["link"] == "https://example.com/doc1"
    assert tool_return.return_value[0]["extra_snippets"] == ["RAG Content 1"]
    assert tool_return.return_value[1]["link"] == "https://example.com/doc2"
    assert tool_return.return_value[1]["extra_snippets"] == ["RAG Content 2"]
    assert tool_return.metadata["sources"] == {
        "https://example.com/doc1",
        "https://example.com/doc2",
    }

    # Verify usage was updated
    assert mock_ctx.usage.input_tokens == 10
    assert mock_ctx.usage.output_tokens == 5


@responses.activate
def test_web_search_brave_with_document_backend_single_worker(settings):
    """Test web_search_brave_with_document_backend with single worker."""
    settings.BRAVE_MAX_WORKERS = 1

    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/single", "title": "Single Doc"},
                ]
            }
        },
        status=200,
    )

    mock_ctx = Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)

    mock_document_store = MagicMock()
    mock_rag_result = Mock(url="https://example.com/single", content="Single Content")
    mock_rag_results = Mock(
        data=[mock_rag_result], usage=Mock(prompt_tokens=5, completion_tokens=3)
    )
    mock_document_store.search.return_value = mock_rag_results

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection.return_value.__enter__.return_value = (
        mock_document_store
    )

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave._fetch_and_store") as mock_store:
            tool_return = web_search_brave_with_document_backend(mock_ctx, "single query")

    assert len(tool_return.return_value) == 1
    mock_store.assert_called_once()


@responses.activate
def test_web_search_brave_with_document_backend_fetch_error(settings):
    """Test web_search_brave_with_document_backend when document fetching fails (multi-worker)."""
    settings.BRAVE_MAX_WORKERS = 2

    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/error", "title": "Error Doc"},
                    {"url": "https://example.com/ok", "title": "OK Doc"},
                ]
            }
        },
        status=200,
    )

    mock_ctx = Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)

    mock_document_store = MagicMock()
    mock_rag_results = Mock(data=[], usage=Mock(prompt_tokens=0, completion_tokens=0))
    mock_document_store.search.return_value = mock_rag_results

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection.return_value.__enter__.return_value = (
        mock_document_store
    )

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave._fetch_and_store") as mock_store:
            # First call fails, second succeeds
            mock_store.side_effect = [Exception("Fetch error"), None]

            tool_return = web_search_brave_with_document_backend(mock_ctx, "error query")

    # Should complete despite error (error is caught and logged in multi-worker path)
    assert tool_return.return_value == []


@responses.activate
def test_web_search_brave_with_document_backend_no_matching_rag_results():
    """
    Test when RAG returns results that don't match any search results.

    This is actually a problematic scenario, but we want to ensure graceful handling.
    """
    responses.add(
        responses.GET,
        BRAVE_URL,
        json={
            "web": {
                "results": [
                    {"url": "https://example.com/doc1", "title": "Document 1"},
                ]
            }
        },
        status=200,
    )

    mock_ctx = Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)

    mock_document_store = MagicMock()
    # RAG result with different URL
    mock_rag_result = Mock(url="https://different.com/doc", content="Different Content")
    mock_rag_results = Mock(
        data=[mock_rag_result], usage=Mock(prompt_tokens=5, completion_tokens=3)
    )
    mock_document_store.search.return_value = mock_rag_results

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection.return_value.__enter__.return_value = (
        mock_document_store
    )

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave.fetch_url") as mock_fetch:
            mock_fetch.return_value = "<html><body>Content</body></html>"

            tool_return = web_search_brave_with_document_backend(mock_ctx, "query")

    # No results should be returned since RAG URL doesn't match search results
    assert tool_return.return_value == []
    assert tool_return.metadata["sources"] == set()


def test_fetch_and_store():
    """Test _fetch_and_store function."""
    mock_document_store = MagicMock()

    with patch("chat.tools.web_search_brave._fetch_and_extract") as mock_extract:
        mock_extract.return_value = "Extracted document content"

        _fetch_and_store("https://example.com/doc", mock_document_store)

        mock_extract.assert_called_once_with("https://example.com/doc")
        mock_document_store.store_document.assert_called_once_with(
            "https://example.com/doc", "Extracted document content"
        )


def test_fetch_and_store_empty_document():
    """Test _fetch_and_store when extraction returns empty document."""
    mock_document_store = MagicMock()

    with patch("chat.tools.web_search_brave._fetch_and_extract") as mock_extract:
        mock_extract.return_value = ""

        _fetch_and_store("https://example.com/empty", mock_document_store)

        # Should not store empty document
        mock_document_store.store_document.assert_not_called()


@responses.activate
def test_query_brave_api_missing_web_key():
    """Test _query_brave_api when response doesn't contain 'web' key."""
    responses.add(
        responses.GET,
        BRAVE_URL,
        json={"error": "no web results"},
        status=200,
    )

    result = _query_brave_api("query")
    assert not result


@responses.activate
def test_query_brave_api_missing_results_key():
    """Test _query_brave_api when 'web' exists but 'results' is missing."""
    responses.add(
        responses.GET,
        BRAVE_URL,
        json={"web": {}},
        status=200,
    )

    result = _query_brave_api("query")
    assert not result
