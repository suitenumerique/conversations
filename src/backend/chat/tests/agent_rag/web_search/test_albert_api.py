"""Unit tests for the Albert API web search manager."""

import json

import pytest
import requests
import responses

from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.web_search.albert_api import AlbertWebSearchManager


@pytest.fixture(autouse=True)
def albert_api_settings(settings):
    """Fixture to set Albert API settings for tests."""
    settings.ALBERT_API_URL = "http://test-albert-api.com"
    settings.ALBERT_API_KEY = "test-key"


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://example.com/page.html", "http://example.com/page"),
        ("http://example.com/page", "http://example.com/page"),
        ("http://example.com/.html", "http://example.com/"),
    ],
)
def test_clean_url(url, expected):
    """Test the _clean_url static method."""
    assert AlbertWebSearchManager._clean_url(url) == expected  # pylint: disable=protected-access


@responses.activate
def test_web_search_success(settings):
    """Test a successful web search."""
    settings.RAG_WEB_SEARCH_MAX_RESULTS = 20
    settings.RAG_WEB_SEARCH_CHUNK_NUMBER = 10

    mock_albert_api = responses.post(
        "http://test-albert-api.com/v1/search",
        json={
            "data": [
                {
                    "method": "semantic",
                    "chunk": {
                        "id": 123,
                        "content": "This is a test chunk.",
                        "metadata": {
                            "document_name": "http://example.com/test.html",
                            "document_type": "html",
                        },
                    },
                    "score": 0.9,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        },
        status=200,
        content_type="application/json",
    )

    results = AlbertWebSearchManager().web_search("test query")
    assert results == RAGWebResults(
        data=[
            RAGWebResult(url="http://example.com/test", content="This is a test chunk.", score=0.9, metadata={})
        ],
        usage=RAGWebUsage(prompt_tokens=10, completion_tokens=20),
    )

    # Verify the request payload
    request = mock_albert_api.calls[0].request
    assert json.loads(request.body) == {
        "prompt": "test query",
        "web_search": True,
        "web_search_k": 20,  # Default value from settings
        "k": 10,  # Default value from settings
    }


def test_web_search_empty_query():
    """Test web_search with an empty query."""
    with pytest.raises(ValueError, match="Search query cannot be empty."):
        AlbertWebSearchManager().web_search("   ")


@responses.activate
def test_web_search_http_error():
    """Test web_search with an HTTP error from the API."""
    responses.post("http://test-albert-api.com/v1/search", status=500)
    with pytest.raises(requests.HTTPError):
        AlbertWebSearchManager().web_search("test query")


@responses.activate
def test_web_search_json_decode_error():
    """Test web_search with a JSON decode error from the API."""
    responses.post(
        "http://test-albert-api.com/v1/search",
        body="invalid json",
        status=200,
        content_type="application/json",
    )

    with pytest.raises(requests.exceptions.JSONDecodeError):
        AlbertWebSearchManager().web_search("test query")
