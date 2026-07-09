"""Tests for the Staan web search tool."""

from unittest.mock import Mock, patch

import pytest

from chat.tools.web_search_staan import resolve_staan_market, staan_search

STAAN_WEB_SEARCH_URL = "https://api.staan.ai/v2/search/web"


@pytest.fixture(autouse=True)
def staan_settings(settings):
    """Define Staan settings for tests."""
    settings.STAAN_API_KEY = "test-staan-key"
    settings.STAAN_SEARCH_ENDPOINT = STAAN_WEB_SEARCH_URL
    settings.STAAN_SEARCH_EXTRA_SNIPPETS = True
    settings.STAAN_API_TIMEOUT = 5
    settings.STAAN_MAX_RESULTS = 10
    settings.STAAN_MAX_SNIPPET_LENGTH = 5000


@pytest.mark.parametrize(
    ("language", "expected_market"),
    [
        ("fr-fr", "fr-fr"),
        ("en-us", "en-us"),
        ("de-de", "de-de"),
        ("FR-FR", "fr-fr"),
        ("nl-nl", "en-us"),
    ],
)
def test_resolve_staan_market_from_language(settings, language, expected_market):
    """Language should map to a supported Staan market."""
    settings.LANGUAGE_CODE = "en-us"

    assert resolve_staan_market(language) == expected_market


def test_resolve_staan_market_falls_back_to_language_code(settings):
    """Missing language should fall back to Django LANGUAGE_CODE."""
    settings.LANGUAGE_CODE = "en-us"

    assert resolve_staan_market(None) == "en-us"


def test_resolve_staan_market_falls_back_to_english_for_unsupported_language(settings):
    """Unsupported languages should fall back to English."""
    settings.LANGUAGE_CODE = "nl-nl"

    assert resolve_staan_market(None) == "en-us"


@patch("chat.tools.web_search_staan.requests.get")
def test_staan_search_sends_market_query_param(mock_get):
    """Market must be forwarded to the Staan API as a query parameter."""
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {
        "query": {"q": "climate tech", "market": "en-us"},
        "web": {"results": []},
    }
    mock_get.return_value = mock_response

    staan_search("climate tech", "en-us")

    mock_get.assert_called_once_with(
        STAAN_WEB_SEARCH_URL,
        params={
            "q": "climate tech",
            "market": "en-us",
            "extra_snippets": "true",
        },
        headers={"Authorization": "Bearer test-staan-key"},
        timeout=5,
    )
