"""Tests for the Staan web search tool."""

from unittest.mock import Mock
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai._run_context import RunContextAgentDepsT

from chat.tools.exceptions import ModelCannotRetry
from chat.tools.web_search_staan import (
    STAAN_SEARCH_PATH,
    format_staan,
    resolve_staan_market,
    staan_search,
    web_search_staan,
)

STAAN_API_URL = "https://api.staan.ai"


@pytest.fixture(name="staan_settings", autouse=True)
def fixture_staan_settings(settings):
    """Define Staan settings for tests."""
    settings.STAAN_API_KEY = "test-staan-key"
    settings.STAAN_API_URL = STAAN_API_URL
    settings.STAAN_SEARCH_EXTRA_SNIPPETS = True
    settings.STAAN_API_TIMEOUT = 5
    settings.STAAN_MAX_SNIPPETS_PER_URL = 3
    settings.STAAN_MIN_SNIPPET_SCORE = 0.1


@pytest.fixture(name="mocked_context")
def fixture_mocked_context():
    """Fixture for a mocked RunContext."""
    mock_ctx = Mock(spec=RunContext)
    mock_ctx.deps = Mock(spec=RunContextAgentDepsT)
    mock_ctx.deps.language = "fr-fr"
    mock_ctx.max_retries = 2
    mock_ctx.retries = {}
    return mock_ctx


@pytest.mark.parametrize(
    ("language", "expected_market"),
    [
        ("fr-fr", "fr-fr"),
        ("en-us", "en-us"),
        ("de-de", "de-de"),
        ("FR-FR", "fr-fr"),
        ("fr", "fr-fr"),
        ("de", "de-de"),
        ("nl-nl", "en-us"),
        (None, "en-us"),
    ],
)
def test_resolve_staan_market_from_language(settings, language, expected_market):
    """Language should map to a supported Staan market."""
    settings.LANGUAGE_CODE = "en-us"

    assert resolve_staan_market(language) == expected_market


@pytest.mark.asyncio
@respx.mock
async def test_staan_search_sends_search_parameters():
    """Market and the API-side limits must be forwarded to the Staan API."""
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(status_code=200, json={"web": {"results": []}}),
    )

    await staan_search("climate tech", "en-us")

    request = respx.calls[0].request
    query_string = parse_qs(request.url.query.decode("utf-8"))

    assert query_string["q"] == ["climate tech"]
    assert query_string["market"] == ["en-us"]
    assert query_string["extra_snippets"] == ["true"]
    assert query_string["max_snippets"] == ["3"]
    assert query_string["min_score"] == ["0.1"]
    assert request.headers["Authorization"] == "Bearer test-staan-key"
    # The API rejects any count other than 10, so we must not send one at all.
    assert "count" not in query_string


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("base_url", ["https://gw.internal/staan", "https://gw.internal/staan/"])
async def test_staan_search_keeps_the_base_url_path(settings, base_url):
    """A base URL pointing at a proxied instance must keep its path segment."""
    settings.STAAN_API_URL = base_url
    route = respx.get(f"https://gw.internal/staan/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(status_code=200, json={"web": {"results": []}}),
    )

    await staan_search("climate tech", "en-us")

    assert route.called


@pytest.mark.asyncio
@pytest.mark.parametrize("setting_name", ["STAAN_API_KEY", "STAAN_API_URL"])
async def test_staan_search_requires_its_settings(settings, setting_name):
    """A missing mandatory setting must be reported before any call is made."""
    setattr(settings, setting_name, None)

    with pytest.raises(ModelCannotRetry, match=setting_name):
        await staan_search("climate tech", "en-us")


def test_format_staan_keeps_snippets_and_published_date():
    """The main snippet, the extra chunks and the publication date must be kept."""
    formatted_results = format_staan(
        {
            "web": {
                "results": [
                    {
                        "url": "https://example.com/1",
                        "title": "Result 1",
                        "snippet": "main snippet",
                        "published_date": "2026-01-15",
                        "extra_snippets": [
                            {"chunk": "first chunk", "score": 0.9},
                            {"chunk": "second chunk", "score": 0.5},
                        ],
                    },
                ]
            }
        }
    )

    assert formatted_results == {
        "0": {
            "url": "https://example.com/1",
            "title": "Result 1",
            "snippets": ["main snippet", "first chunk", "second chunk"],
            "published_date": "2026-01-15",
        }
    }


def test_format_staan_drops_results_without_snippet_or_url():
    """Results the model cannot use must not reach the context nor the citations."""
    formatted_results = format_staan(
        {
            "web": {
                "results": [
                    {"url": "https://example.com/no-snippet", "title": "No snippet"},
                    {"title": "No url", "snippet": "orphan snippet"},
                    {"url": "https://example.com/ok", "title": "Ok", "snippet": "kept"},
                ]
            }
        }
    )

    assert list(formatted_results) == ["0"]
    assert formatted_results["0"]["url"] == "https://example.com/ok"


def test_format_staan_keeps_every_chunk_whole():
    """Chunks are kept as the API ranked them: none is trimmed, none is dropped for size."""
    formatted_results = format_staan(
        {
            "web": {
                "results": [
                    {
                        "url": "https://example.com/1",
                        "title": "Result 1",
                        "extra_snippets": [
                            {"chunk": "a" * 1800, "score": 0.9},
                            {"chunk": "small chunk", "score": 0.8},
                        ],
                    },
                ]
            }
        }
    )

    assert formatted_results["0"]["snippets"] == ["a" * 1800, "small chunk"]


def test_format_staan_skips_unusable_results_without_leaving_gaps():
    """Results missing a url or a snippet must be skipped, keeping ranks contiguous."""
    formatted_results = format_staan(
        {
            "web": {
                "results": [
                    {"url": "https://example.com/no-snippet"},
                    {"snippet": "no url"},
                    {"url": "https://example.com/1", "snippet": "snippet 1"},
                    {"url": "https://example.com/2", "snippet": "snippet 2"},
                    {"url": "https://example.com/3", "snippet": "snippet 3"},
                ]
            }
        }
    )

    assert list(formatted_results) == ["0", "1", "2"]
    assert [result["url"] for result in formatted_results.values()] == [
        "https://example.com/1",
        "https://example.com/2",
        "https://example.com/3",
    ]


@pytest.mark.asyncio
@respx.mock
async def test_web_search_staan_success(mocked_context):
    """A successful search returns the formatted results and their sources."""
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "query": {"market": "fr-fr"},
                "web": {
                    "results": [
                        {
                            "url": "https://example.com/1",
                            "title": "Result 1",
                            "snippet": "main snippet",
                        },
                        {"url": "https://example.com/no-snippet", "title": "No snippet"},
                    ]
                },
            },
        ),
    )

    tool_return = await web_search_staan(mocked_context, "actualité")

    assert tool_return.return_value["0"]["url"] == "https://example.com/1"
    assert tool_return.metadata["sources"] == {"https://example.com/1"}


@pytest.mark.asyncio
@respx.mock
async def test_web_search_staan_empty_results(mocked_context):
    """No usable result must let the model retry instead of answering from memory."""
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(status_code=200, json={"web": {"results": []}}),
    )

    with pytest.raises(ModelRetry) as exc:
        await web_search_staan(mocked_context, "empty query")

    assert "No valid search results" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_web_search_staan_missing_web_key(mocked_context):
    """An unexpected payload must not crash the tool."""
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(status_code=200, json={"query": {"market": "fr-fr"}}),
    )

    with pytest.raises(ModelRetry) as exc:
        await web_search_staan(mocked_context, "weird payload")

    assert "No valid search results" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_web_search_staan_retryable_http_errors(mocked_context, status_code):
    """Rate limiting and server errors must be retryable."""
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(status_code=status_code, json={"error": "nope"}),
    )

    with pytest.raises(ModelRetry):
        await web_search_staan(mocked_context, "error query")


@pytest.mark.asyncio
@respx.mock
async def test_web_search_staan_client_error_is_not_retryable(mocked_context):
    """A client error must stop the search and be explained to the user."""
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(status_code=400, json={"error": "bad request"}),
    )

    tool_return = await web_search_staan(mocked_context, "error query")

    assert "client error (status 400)" in tool_return
    assert "not try to answer based on your knowledge" in tool_return


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "side_effect",
    [httpx.ConnectTimeout("timeout"), httpx.ConnectError("connection refused")],
)
async def test_web_search_staan_network_errors_are_retryable(mocked_context, side_effect):
    """Transient network failures must be retryable, not dead ends."""
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(side_effect=side_effect)

    with pytest.raises(ModelRetry):
        await web_search_staan(mocked_context, "network error")


@pytest.mark.asyncio
@respx.mock
async def test_web_search_staan_soft_fails_on_last_retry(mocked_context):
    """On the last retry the tool must return a message instead of raising."""
    mocked_context.tool_name = "web_search"
    mocked_context.retries = {"web_search": 1}
    respx.get(f"{STAAN_API_URL}/{STAAN_SEARCH_PATH}").mock(
        return_value=httpx.Response(status_code=200, json={"web": {"results": []}}),
    )

    tool_return = await web_search_staan(mocked_context, "empty query")

    assert "not try to answer based on your knowledge" in tool_return
