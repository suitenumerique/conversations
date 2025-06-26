"""Test cases for Tavily web search tool."""

import json

import pytest
import responses

from chat.tools.web_search_tavily import tavily_web_search

TAVILY_URL = "https://api.tavily.com/search"


@pytest.fixture(autouse=True)
def tavily_settings(settings):
    """Set up Tavily settings for tests."""
    settings.TAVILY_API_KEY = "test_api_key"
    settings.TAVILY_MAX_RESULTS = 3
    settings.TAVILY_API_TIMEOUT = 5


@responses.activate
def test_agent_web_search_tavily_success():
    """Test successful Tavily web search."""
    responses.add(
        responses.POST,
        TAVILY_URL,
        json={
            "results": [
                {"url": "https://example.com/1", "title": "Result 1", "content": "Snippet 1"},
                {"url": "https://example.com/2", "title": "Result 2", "content": "Snippet 2"},
            ]
        },
        status=200,
    )
    results = tavily_web_search("test query")
    assert results == [
        {"link": "https://example.com/1", "title": "Result 1", "snippet": "Snippet 1"},
        {"link": "https://example.com/2", "title": "Result 2", "snippet": "Snippet 2"},
    ]

    # Check request payload
    tavily_request = responses.calls[0].request
    payload = json.loads(tavily_request.body.decode("utf-8"))
    assert payload["query"] == "test query"
    assert payload["api_key"] == "test_api_key"
    assert payload["max_results"] == 3


@responses.activate
def test_agent_web_search_tavily_empty_results():
    """Test Tavily web search with no results."""
    responses.add(
        responses.POST,
        TAVILY_URL,
        json={"results": []},
        status=200,
    )
    results = tavily_web_search("no results query")
    assert results == []


@responses.activate
def test_agent_web_search_tavily_http_error():
    """Test Tavily web search with HTTP error."""
    responses.add(
        responses.POST,
        TAVILY_URL,
        status=500,
        json={"error": "Internal Server Error"},
    )
    with pytest.raises(Exception) as exc:
        tavily_web_search("error query")
    assert "500" in str(exc.value) or "Internal Server Error" in str(exc.value)
