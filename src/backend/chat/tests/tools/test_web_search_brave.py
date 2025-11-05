"""Tests for the Brave web search tool."""

# pylint: disable=too-many-lines

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from pydantic_ai import ModelRetry, RunContext, RunUsage

from chat.tools.exceptions import ModelCannotRetry
from chat.tools.web_search_brave import (
    DocumentFetchError,
    _extract_and_summarize_snippets_async,
    _fetch_and_extract_async,
    _fetch_and_store_async,
    _query_brave_api_async,
    format_tool_return,
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
    settings.BRAVE_CACHE_TTL = 3600
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER = 5


@pytest.fixture(name="mocked_context")
def fixture_mocked_context():
    """Fixture for a mocked RunContext."""
    mock_ctx = Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)
    mock_ctx.max_retries = 2
    mock_ctx.retries = {}
    return mock_ctx


@pytest.mark.asyncio
@respx.mock
async def test_agent_web_search_brave_success_with_extra_snippets(mocked_context):
    """Test when the Brave search returns results with extra_snippets."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
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
        )
    )

    with patch("chat.tools.web_search_brave._fetch_url_async") as mock_fetch:
        # Fetch should not be called since extra_snippets are provided
        mock_fetch.side_effect = Exception("fetch_url should not be called")
        tool_return = await web_search_brave(mocked_context, "test query")

    assert hasattr(tool_return, "return_value")
    assert tool_return.return_value == {
        "0": {
            "snippets": ["Snippet A1", "Snippet A2"],
            "title": "Result A",
            "url": "https://example.com/a",
        },
        "1": {"snippets": ["Snippet B1"], "title": "Result B", "url": "https://example.com/b"},
    }
    assert tool_return.metadata["sources"] == {"https://example.com/a", "https://example.com/b"}

    # Check request parameters
    brave_request = respx.calls[0].request
    qs = parse_qs(brave_request.url.query.decode("utf-8"))
    assert qs["q"] == ["test query"]
    assert qs["count"] == ["3"]
    assert qs["search_lang"] == ["en"]
    assert qs["country"] == ["US"]
    assert qs["safesearch"] == ["moderate"]
    assert qs["spellcheck"] == ["true"]
    assert qs["extra_snippets"] == ["true"]
    assert qs["result_filter"] == ["web,faq,query"]


@pytest.mark.asyncio
@respx.mock
async def test_agent_web_search_brave_success_without_extra_snippets(mocked_context):
    """Test when the Brave search returns results without extra_snippets."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/c", "title": "Result C"},  # no extra_snippets
                    ]
                }
            },
        )
    )

    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            mock_fetch.return_value = (
                '<html><body>Extracted Content C<a href="url">link</a></body></html>'
            )
            mock_extract.return_value = "Extracted Content C\nlink"

            with patch("chat.tools.web_search_brave.cache") as mock_cache:
                mock_cache.aget = AsyncMock(return_value=None)
                mock_cache.aset = AsyncMock()

                tool_return = await web_search_brave(mocked_context, "test query")

    assert tool_return.return_value == {
        "0": {
            "snippets": ["Extracted Content C\nlink"],
            "title": "Result C",
            "url": "https://example.com/c",
        }
    }
    assert tool_return.metadata["sources"] == {"https://example.com/c"}


@pytest.mark.asyncio
@respx.mock
async def test_agent_web_search_brave_success_without_extra_snippets_summarization(
    settings, mocked_context
):
    """Test when the Brave search returns results without extra_snippets with summarization."""
    settings.BRAVE_SUMMARIZATION_ENABLED = True

    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/c", "title": "Result C"},  # no extra_snippets
                    ]
                }
            },
        )
    )

    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            with patch(
                "chat.tools.web_search_brave.llm_summarize_async", new_callable=AsyncMock
            ) as mock_summarize:
                mock_fetch.return_value = (
                    '<html><body>Extracted Content C<a href="url">link</a></body></html>'
                )
                mock_extract.return_value = "Extracted Content C\nlink"
                mock_summarize.return_value = "Summarized extracted Content C\nlink"

                with patch("chat.tools.web_search_brave.cache") as mock_cache:
                    mock_cache.aget = AsyncMock(return_value=None)
                    mock_cache.aset = AsyncMock()

                    tool_return = await web_search_brave(mocked_context, "test query")

                mock_summarize.assert_called_with("test query", "Extracted Content C\nlink")

    assert tool_return.return_value == {
        "0": {
            "snippets": ["Summarized extracted Content C\nlink"],
            "title": "Result C",
            "url": "https://example.com/c",
        }
    }
    assert tool_return.metadata["sources"] == {"https://example.com/c"}


@pytest.mark.asyncio
@respx.mock
async def test_agent_web_search_brave_empty_results(mocked_context):
    """Test when the Brave search returns no results."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={"web": {"results": []}},
        ),
    )

    with pytest.raises(ModelRetry) as exc:
        await web_search_brave(mocked_context, "empty query")

    assert "No valid search results" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_agent_web_search_brave_http_error(mocked_context):
    """Test handling of HTTP errors from Brave API."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=500,
            json={"error": "Internal Server Error"},
        )
    )

    with pytest.raises(ModelRetry) as exc:
        await web_search_brave(mocked_context, "error query")

    assert (
        "server error" in str(exc.value).lower()
        or "temporarily unavailable" in str(exc.value).lower()
    )


@pytest.mark.asyncio
@respx.mock
async def test_agent_web_search_brave_params_exclude_none(settings, mocked_context):
    """Check that None parameters are excluded from the request."""
    settings.BRAVE_SEARCH_COUNTRY = None
    settings.BRAVE_SEARCH_LANG = None

    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={"web": {"results": []}},
        ),
    )

    with pytest.raises(ModelRetry):  # Will raise due to empty results
        await web_search_brave(mocked_context, "none params")

    brave_request = respx.calls[0].request
    qs = parse_qs(brave_request.url.query.decode("utf-8"))

    # Mandatory params
    assert qs["q"] == ["none params"]
    assert qs["count"] == ["3"]

    # None params missing
    assert "country" not in qs
    assert "search_lang" not in qs

    # Defined params present
    assert qs["safesearch"] == ["moderate"]
    assert qs["spellcheck"] == ["true"]
    assert qs["extra_snippets"] == ["true"]

    # Empty body for GET request
    assert not brave_request.content


@pytest.mark.asyncio
@respx.mock
async def test_agent_web_search_brave_concurrent_processing(mocked_context):
    """Test concurrent processing with asyncio.gather."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/1", "title": "Result 1"},
                        {"url": "https://example.com/2", "title": "Result 2"},
                    ]
                }
            },
        )
    )

    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            mock_fetch.return_value = "<html><body>Content</body></html>"
            mock_extract.return_value = "Content"

            with patch("chat.tools.web_search_brave.cache") as mock_cache:
                mock_cache.aget = AsyncMock(return_value=None)
                mock_cache.aset = AsyncMock()

                tool_return = await web_search_brave(mocked_context, "parallel query")

    assert len(tool_return.return_value) == 2
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_fetch_and_extract_with_cache():
    """Test caching mechanism in _fetch_and_extract_async."""
    with patch("chat.tools.web_search_brave.cache") as mock_cache:
        with patch(
            "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
        ) as mock_fetch:
            with patch("chat.tools.web_search_brave.extract") as mock_extract:
                # First call - cache miss
                mock_cache.aget = AsyncMock(return_value=None)
                mock_cache.aset = AsyncMock()
                mock_fetch.return_value = "<html><body>Cached Content</body></html>"
                mock_extract.return_value = "Cached Content"

                result1 = await _fetch_and_extract_async("https://example.com/cache")

                assert result1 == "Cached Content"
                mock_cache.aget.assert_called_once()
                mock_cache.aset.assert_called_once()

                # Second call - cache hit
                mock_cache.aget = AsyncMock(return_value="Cached Content")
                result2 = await _fetch_and_extract_async("https://example.com/cache")

                assert result2 == "Cached Content"
                # fetch_url should still be called only once (from first call)
                assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_extract_and_summarize_snippets_empty_document():
    """Test _extract_and_summarize_snippets_async when extraction returns empty string."""
    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            with patch("chat.tools.web_search_brave.cache") as mock_cache:
                mock_cache.aget = AsyncMock(return_value=None)
                mock_cache.aset = AsyncMock()
                mock_fetch.return_value = "<html><body></body></html>"
                mock_extract.return_value = ""

                result = await _extract_and_summarize_snippets_async(
                    "query", "https://example.com/empty"
                )

                assert not result


@pytest.mark.asyncio
async def test_extract_and_summarize_snippets_summarization_failure(settings):
    """Test _extract_and_summarize_snippets_async when summarization fails."""
    settings.BRAVE_SUMMARIZATION_ENABLED = True

    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            with patch(
                "chat.tools.web_search_brave.llm_summarize_async", new_callable=AsyncMock
            ) as mock_summarize:
                with patch("chat.tools.web_search_brave.cache") as mock_cache:
                    mock_cache.aget = AsyncMock(return_value=None)
                    mock_cache.aset = AsyncMock()
                    mock_fetch.return_value = "<html><body>Content</body></html>"
                    mock_extract.return_value = "Content"
                    mock_summarize.side_effect = Exception("Summarization error")

                    result = await _extract_and_summarize_snippets_async(
                        "query", "https://example.com/error"
                    )

                    # Should return raw document as fallback
                    assert result == ["Content"]


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_success(mocked_context):
    """Test web_search_brave_with_document_backend with successful RAG search."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/doc1", "title": "Document 1"},
                        {"url": "https://example.com/doc2", "title": "Document 2"},
                    ],
                },
            },
        )
    )

    mock_document_store = MagicMock()
    mock_rag_result1 = Mock(url="https://example.com/doc1", content="RAG Content 1")
    mock_rag_result2 = Mock(url="https://example.com/doc2", content="RAG Content 2")
    mock_rag_results = Mock(
        data=[mock_rag_result1, mock_rag_result2], usage=Mock(prompt_tokens=10, completion_tokens=5)
    )
    mock_document_store.asearch = AsyncMock(return_value=mock_rag_results)

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection_async.return_value.__aenter__ = AsyncMock(
        return_value=mock_document_store
    )
    mock_backend_class.temporary_collection_async.return_value.__aexit__ = AsyncMock()

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave._fetch_and_store_async", new_callable=AsyncMock):
            tool_return = await web_search_brave_with_document_backend(mocked_context, "rag query")

    assert len(tool_return.return_value) == 2
    assert tool_return.return_value["0"]["url"] == "https://example.com/doc1"
    assert tool_return.return_value["0"]["snippets"] == ["RAG Content 1"]
    assert tool_return.return_value["1"]["url"] == "https://example.com/doc2"
    assert tool_return.return_value["1"]["snippets"] == ["RAG Content 2"]
    assert tool_return.metadata["sources"] == {
        "https://example.com/doc1",
        "https://example.com/doc2",
    }

    # Verify usage was updated
    assert mocked_context.usage.input_tokens == 10
    assert mocked_context.usage.output_tokens == 5


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_fetch_error(mocked_context):
    """Test web_search_brave_with_document_backend when document fetching fails."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/error", "title": "Error Doc"},
                        {"url": "https://example.com/ok", "title": "OK Doc"},
                    ]
                }
            },
        )
    )

    mock_document_store = MagicMock()
    mock_rag_results = Mock(data=[], usage=Mock(prompt_tokens=0, completion_tokens=0))
    mock_document_store.asearch = AsyncMock(return_value=mock_rag_results)

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection_async.return_value.__aenter__ = AsyncMock(
        return_value=mock_document_store
    )
    mock_backend_class.temporary_collection_async.return_value.__aexit__ = AsyncMock()

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch(
            "chat.tools.web_search_brave._fetch_and_store_async", new_callable=AsyncMock
        ) as mock_store:
            # First call fails, second succeeds
            mock_store.side_effect = [Exception("Fetch error"), None]

            with pytest.raises(ModelRetry):
                await web_search_brave_with_document_backend(mocked_context, "error query")


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_no_matching_rag_results(mocked_context):
    """
    Test when RAG returns results that don't match any search results.

    This is actually a problematic scenario, but we want to ensure graceful handling.
    """
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/doc1", "title": "Document 1"},
                    ]
                }
            },
        )
    )

    mock_document_store = MagicMock()
    # RAG result with different URL
    mock_rag_result = Mock(url="https://different.com/doc", content="Different Content")
    mock_rag_results = Mock(
        data=[mock_rag_result], usage=Mock(prompt_tokens=5, completion_tokens=3)
    )
    mock_document_store.asearch = AsyncMock(return_value=mock_rag_results)

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection_async.return_value.__aenter__ = AsyncMock(
        return_value=mock_document_store
    )
    mock_backend_class.temporary_collection_async.return_value.__aexit__ = AsyncMock()

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave._fetch_and_store_async", new_callable=AsyncMock):
            with pytest.raises(ModelRetry):
                await web_search_brave_with_document_backend(mocked_context, "query")


@pytest.mark.asyncio
async def test_fetch_and_store():
    """Test _fetch_and_store_async function."""
    mock_document_store = AsyncMock()

    with patch(
        "chat.tools.web_search_brave._fetch_and_extract_async", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.return_value = "Extracted document content"

        await _fetch_and_store_async("https://example.com/doc", mock_document_store)

        mock_extract.assert_called_once_with("https://example.com/doc")
        mock_document_store.astore_document.assert_called_once_with(
            "https://example.com/doc", "Extracted document content"
        )


@pytest.mark.asyncio
async def test_fetch_and_store_empty_document():
    """Test _fetch_and_store_async when extraction returns empty document."""
    mock_document_store = MagicMock()

    with patch(
        "chat.tools.web_search_brave._fetch_and_extract_async", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.return_value = ""

        await _fetch_and_store_async("https://example.com/empty", mock_document_store)

        # Should not store empty document
        mock_document_store.store_document.assert_not_called()


@pytest.mark.asyncio
@respx.mock
async def test_query_brave_api_missing_web_key():
    """Test _query_brave_api_async when response doesn't contain 'web' key."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={"error": "no web results"},
        )
    )

    result = await _query_brave_api_async("query")
    assert not result


@pytest.mark.asyncio
@respx.mock
async def test_query_brave_api_missing_results_key():
    """Test _query_brave_api_async when 'web' exists but 'results' is missing."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={"web": {}},
        )
    )
    result = await _query_brave_api_async("query")
    assert not result


@pytest.mark.asyncio
@respx.mock
async def test_query_brave_api_rate_limit():
    """Test _query_brave_api_async handles 429 rate limit errors."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=429,
            json={"error": "Rate limit exceeded"},
        )
    )

    with pytest.raises(ModelRetry) as exc:
        await _query_brave_api_async("query")

    assert "rate limited" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_query_brave_api_client_error():
    """Test _query_brave_api_async handles 4xx client errors."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=400,
            json={"error": "Bad request"},
        )
    )

    with pytest.raises(ModelCannotRetry) as exc:
        await _query_brave_api_async("query")

    assert "client error" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_query_brave_api_timeout():
    """Test _query_brave_api_async handles timeout errors."""
    respx.get(BRAVE_URL).mock(side_effect=httpx.TimeoutException("Request timed out"))

    with pytest.raises(ModelRetry) as exc:
        await _query_brave_api_async("query")

    assert "timed out" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_query_brave_api_generic_http_error():
    """Test _query_brave_api_async handles generic HTTP errors."""
    respx.get(BRAVE_URL).mock(side_effect=httpx.ConnectError("Connection failed"))

    with pytest.raises(ModelRetry) as exc:
        await _query_brave_api_async("query")

    assert "connection error" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_query_brave_api_unexpected_error():
    """Test _query_brave_api_async handles unexpected errors."""
    respx.get(BRAVE_URL).mock(side_effect=ValueError("Unexpected value error"))

    with pytest.raises(ModelCannotRetry) as exc:
        await _query_brave_api_async("query")

    assert "unexpected error" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_fetch_and_extract_extraction_returns_none():
    """Test _fetch_and_extract_async when extract returns None."""
    with patch("chat.tools.web_search_brave.cache") as mock_cache:
        with patch(
            "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
        ) as mock_fetch:
            with patch("chat.tools.web_search_brave.extract") as mock_extract:
                mock_cache.aget = AsyncMock(return_value=None)
                mock_cache.aset = AsyncMock()
                mock_fetch.return_value = "<html><body>Content</body></html>"
                mock_extract.return_value = None

                result = await _fetch_and_extract_async("https://example.com/none")

                assert result is None
                mock_cache.aset.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_and_extract_http_error():
    """Test _fetch_and_extract_async when HTTP fetch fails."""
    with patch("chat.tools.web_search_brave.cache") as mock_cache:
        with patch(
            "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
        ) as mock_fetch:
            mock_cache.aget = AsyncMock(return_value=None)
            mock_fetch.side_effect = httpx.HTTPError("Network error")
            with pytest.raises(DocumentFetchError):
                await _fetch_and_extract_async("https://example.com/error")


@pytest.mark.asyncio
async def test_fetch_and_extract_extraction_exception():
    """Test _fetch_and_extract_async when extract raises an exception."""
    with patch("chat.tools.web_search_brave.cache") as mock_cache:
        with patch(
            "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
        ) as mock_fetch:
            with patch("chat.tools.web_search_brave.extract") as mock_extract:
                mock_cache.aget = AsyncMock(return_value=None)
                mock_fetch.return_value = "<html><body>Content</body></html>"
                mock_extract.side_effect = Exception("Extraction failed")

                with pytest.raises(DocumentFetchError):
                    await _fetch_and_extract_async("https://example.com/extract-error")


@pytest.mark.asyncio
async def test_extract_and_summarize_snippets_fetch_error():
    """Test _extract_and_summarize_snippets_async when document fetch fails."""
    with patch(
        "chat.tools.web_search_brave._fetch_and_extract_async", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.side_effect = DocumentFetchError("Failed to fetch")

        result = await _extract_and_summarize_snippets_async("query", "https://example.com/error")

        assert result == []


@pytest.mark.asyncio
async def test_extract_and_summarize_snippets_summarization_returns_empty(settings):
    """Test _extract_and_summarize_snippets_async when summarization returns empty string."""
    settings.BRAVE_SUMMARIZATION_ENABLED = True

    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            with patch(
                "chat.tools.web_search_brave.llm_summarize_async", new_callable=AsyncMock
            ) as mock_summarize:
                with patch("chat.tools.web_search_brave.cache") as mock_cache:
                    mock_cache.aget = AsyncMock(return_value=None)
                    mock_cache.aset = AsyncMock()
                    mock_fetch.return_value = "<html><body>Content</body></html>"
                    mock_extract.return_value = "Content"
                    mock_summarize.return_value = ""

                    result = await _extract_and_summarize_snippets_async(
                        "query", "https://example.com/empty-summary"
                    )

                    assert result == []


@pytest.mark.asyncio
async def test_fetch_and_store_extraction_error():
    """Test _fetch_and_store_async when extraction fails."""
    mock_document_store = MagicMock()

    with patch(
        "chat.tools.web_search_brave._fetch_and_extract_async", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.side_effect = DocumentFetchError("Extraction failed")

        # Should not raise, just log warning
        await _fetch_and_store_async("https://example.com/error", mock_document_store)

        mock_document_store.store_document.assert_not_called()


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_mixed_results(mocked_context):
    """Test web_search_brave with mixed results (some with snippets, some without)."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://example.com/with",
                            "title": "With Snippets",
                            "extra_snippets": ["Snippet 1"],
                        },
                        {
                            "url": "https://example.com/without",
                            "title": "Without Snippets",
                        },
                    ]
                }
            },
        )
    )

    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            with patch("chat.tools.web_search_brave.cache") as mock_cache:
                mock_cache.aget = AsyncMock(return_value=None)
                mock_cache.aset = AsyncMock()
                mock_fetch.return_value = "<html><body>Extracted</body></html>"
                mock_extract.return_value = "Extracted"

                tool_return = await web_search_brave(mocked_context, "mixed query")

    assert len(tool_return.return_value) == 2
    assert tool_return.return_value["0"]["snippets"] == ["Snippet 1"]
    assert tool_return.return_value["1"]["snippets"] == ["Extracted"]
    # Only one fetch should have happened (for the one without snippets)
    assert mock_fetch.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_extraction_fails_for_all(mocked_context):
    """Test web_search_brave when extraction fails for all results without snippets."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/fail1", "title": "Fail 1"},
                        {"url": "https://example.com/fail2", "title": "Fail 2"},
                    ]
                }
            },
        )
    )

    with patch(
        "chat.tools.web_search_brave._fetch_url_async", new_callable=AsyncMock
    ) as mock_fetch:
        with patch("chat.tools.web_search_brave.extract") as mock_extract:
            with patch("chat.tools.web_search_brave.cache") as mock_cache:
                mock_cache.aget = AsyncMock(return_value=None)
                mock_fetch.side_effect = httpx.HTTPError("Failed")
                mock_extract.return_value = ""

                with pytest.raises(ModelRetry) as exc:
                    await web_search_brave(mocked_context, "fail query")

                assert "no valid search results" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_model_cannot_retry_exception(mocked_context):
    """Test web_search_brave handling of ModelCannotRetry from API."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=403,
            json={"error": "Forbidden"},
        )
    )

    result = await web_search_brave(mocked_context, "forbidden query")
    assert result == (
        "Web search failed with a client error (status 403). "
        "You must explain this to the user and not try to answer based on your knowledge."
    )


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_unexpected_exception(mocked_context):
    """Test web_search_brave handling of unexpected exceptions."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://example.com/ok",
                            "title": "OK",
                            "extra_snippets": ["snippet"],
                        },
                    ]
                }
            },
        )
    )

    with patch("chat.tools.web_search_brave.format_tool_return") as mock_format:
        mock_format.side_effect = RuntimeError("Unexpected error")

        result = await web_search_brave(mocked_context, "error query")
        assert result == (
            "An unexpected error occurred during web search: RuntimeError. You must "
            "explain this to the user and not try to answer based on your knowledge."
        )


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_empty_rag_results(mocked_context):
    """Test web_search_brave_with_document_backend when RAG search returns empty results."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/doc1", "title": "Document 1"},
                    ]
                }
            },
        )
    )

    mock_document_store = MagicMock()
    mock_rag_results = Mock(data=[], usage=Mock(prompt_tokens=0, completion_tokens=0))
    mock_document_store.asearch = AsyncMock(return_value=mock_rag_results)

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection_async.return_value.__aenter__ = AsyncMock(
        return_value=mock_document_store
    )
    mock_backend_class.temporary_collection_async.return_value.__aexit__ = AsyncMock()

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave._fetch_and_store_async", new_callable=AsyncMock):
            with pytest.raises(ModelRetry) as exc:
                await web_search_brave_with_document_backend(mocked_context, "empty query")

            assert "no valid search results" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_store_exception(mocked_context):
    """Test web_search_brave_with_document_backend when document store raises exception."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/doc1", "title": "Document 1"},
                    ]
                }
            },
        )
    )

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection_async.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("Store initialization failed")
    )

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with pytest.raises(ModelRetry) as exc:
            await web_search_brave_with_document_backend(mocked_context, "store error query")

        assert "document storage temporarily failed" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_unexpected_exception(mocked_context):
    """Test web_search_brave_with_document_backend handling of unexpected exceptions."""
    respx.get(BRAVE_URL).mock(side_effect=TypeError("Unexpected type error"))

    result = await web_search_brave_with_document_backend(mocked_context, "error query")
    assert result == (
        "An unexpected error occurred with the search service: TypeError. You must "
        "explain this to the user and not try to answer based on your knowledge."
    )


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_model_cannot_retry(mocked_context):
    """Test web_search_brave_with_document_backend handling of ModelCannotRetry."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=401,
            json={"error": "Unauthorized"},
        )
    )

    result = await web_search_brave_with_document_backend(mocked_context, "unauthorized query")
    assert result == (
        "Web search failed with a client error (status 401). You must explain this to "
        "the user and not try to answer based on your knowledge."
    )


@pytest.mark.asyncio
@respx.mock
async def test_web_search_brave_with_document_backend_rag_search_params(mocked_context):
    """Test web_search_brave_with_document_backend passes correct parameters to RAG search."""
    respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"url": "https://example.com/doc1", "title": "Document 1"},
                    ]
                }
            },
        )
    )

    mock_document_store = MagicMock()
    mock_rag_result = Mock(url="https://example.com/doc1", content="RAG Content")
    mock_rag_results = Mock(
        data=[mock_rag_result], usage=Mock(prompt_tokens=10, completion_tokens=5)
    )
    mock_document_store.asearch = AsyncMock(return_value=mock_rag_results)

    mock_backend_class = MagicMock()
    mock_backend_class.temporary_collection_async.return_value.__aenter__ = AsyncMock(
        return_value=mock_document_store
    )
    mock_backend_class.temporary_collection_async.return_value.__aexit__ = AsyncMock()

    with patch("chat.tools.web_search_brave.import_string", return_value=mock_backend_class):
        with patch("chat.tools.web_search_brave._fetch_and_store_async", new_callable=AsyncMock):
            await web_search_brave_with_document_backend(mocked_context, "test query")

    # Verify RAG search was called with correct parameters
    mock_document_store.asearch.assert_called_once_with("test query", results_count=5)


@pytest.mark.asyncio
async def test_fetch_and_store_none_document():
    """Test _fetch_and_store_async when extraction returns None instead of empty string."""
    mock_document_store = MagicMock()

    with patch(
        "chat.tools.web_search_brave._fetch_and_extract_async", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.return_value = None

        await _fetch_and_store_async("https://example.com/none", mock_document_store)

        # Should not store None document
        mock_document_store.store_document.assert_not_called()


def test_format_tool_return():
    """Test format_tool_return function directly."""

    raw_results = [
        {
            "url": "https://example.com/1",
            "title": "Result 1",
            "extra_snippets": ["Snippet 1A", "Snippet 1B"],
        },
        {
            "url": "https://example.com/2",
            "title": "Result 2",
            "extra_snippets": ["Snippet 2A"],
        },
        {
            "url": "https://example.com/3",
            "title": "Result 3",
            # No extra_snippets
        },
    ]

    tool_return = format_tool_return(raw_results)

    # Result without snippets should be excluded
    assert len(tool_return.return_value) == 2
    assert tool_return.return_value["0"]["url"] == "https://example.com/1"
    assert tool_return.return_value["0"]["title"] == "Result 1"
    assert tool_return.return_value["0"]["snippets"] == ["Snippet 1A", "Snippet 1B"]
    assert tool_return.return_value["1"]["url"] == "https://example.com/2"
    assert tool_return.return_value["1"]["title"] == "Result 2"
    assert tool_return.return_value["1"]["snippets"] == ["Snippet 2A"]

    # Sources should only include URLs with snippets
    assert tool_return.metadata["sources"] == {
        "https://example.com/1",
        "https://example.com/2",
    }


def test_format_tool_return_empty_snippets():
    """Test format_tool_return with results that have empty snippet arrays."""

    raw_results = [
        {
            "url": "https://example.com/1",
            "title": "Result 1",
            "extra_snippets": [],  # Empty array
        },
    ]

    tool_return = format_tool_return(raw_results)

    # Result with empty snippets should be excluded
    assert len(tool_return.return_value) == 0
    assert len(tool_return.metadata["sources"]) == 0


def test_format_tool_return_no_results():
    """Test format_tool_return with empty results list."""

    tool_return = format_tool_return([])

    assert len(tool_return.return_value) == 0
    assert len(tool_return.metadata["sources"]) == 0
