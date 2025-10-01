"""Tests for the Brave web search tool."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from chat.tools.web_search_brave import web_search_brave

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
