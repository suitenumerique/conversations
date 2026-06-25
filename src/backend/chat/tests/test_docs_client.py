"""Tests for the DocsClient."""

from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied

import pytest
import requests

from chat.docs_client import DocsClient


@pytest.fixture(name="docs_client")
def docs_client_fixture(settings):
    """Instantiate a DocsClient with test settings."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.DOCS_API_TIMEOUT = 10
    return DocsClient()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_docs_client_init_api_url(settings):
    """api_url must be the base URL joined with the versioned API path."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.DOCS_API_TIMEOUT = 15
    client = DocsClient()
    assert client.api_url == "http://docs.example.com/external_api/v1.0/"


def test_docs_client_init_api_url_without_trailing_slash(settings):
    """DOCS_BASE_URL without a trailing slash must still produce a correct api_url."""
    settings.DOCS_BASE_URL = "http://docs.example.com"
    settings.DOCS_API_TIMEOUT = 10
    client = DocsClient()
    # urljoin("http://docs.example.com", "external_api/v1.0/") →
    # "http://docs.example.com/external_api/v1.0/"
    assert client.api_url == "http://docs.example.com/external_api/v1.0/"


def test_docs_client_init_timeout(settings):
    """timeout must be taken from DOCS_API_TIMEOUT."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.DOCS_API_TIMEOUT = 42
    client = DocsClient()
    assert client.timeout == 42


# ---------------------------------------------------------------------------
# get_access_token
# ---------------------------------------------------------------------------


def test_get_access_token_returns_token(docs_client):
    """get_access_token returns the token stored in the session."""
    session = {"oidc_access_token": "my-secret-token"}
    assert docs_client.get_access_token(session) == "my-secret-token"


def test_get_access_token_raises_when_missing(docs_client):
    """get_access_token raises PermissionDenied when the session has no token."""
    with pytest.raises(PermissionDenied):
        docs_client.get_access_token({})


def test_get_access_token_raises_when_none(docs_client):
    """get_access_token raises PermissionDenied when the token is None."""
    with pytest.raises(PermissionDenied):
        docs_client.get_access_token({"oidc_access_token": None})


# ---------------------------------------------------------------------------
# create_document
# ---------------------------------------------------------------------------


def test_create_document_success(docs_client):
    """create_document posts to the correct URL and returns parsed JSON."""
    session = {"oidc_access_token": "tok123"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc", "url": "http://docs.example.com/doc-abc"}

    with patch("requests.post", return_value=fake_response) as mock_post:
        result = docs_client.create_document(
            title="My Document", content="# Hello\n\nWorld", session=session
        )

    assert result == {"id": "doc-abc", "url": "http://docs.example.com/doc-abc"}
    mock_post.assert_called_once()


def test_create_document_posts_to_correct_url(docs_client):
    """create_document POSTs to <api_url>documents/."""
    session = {"oidc_access_token": "tok123"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc"}

    with patch("requests.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="Title", content="body", session=session)

    call_args = mock_post.call_args
    assert call_args.args[0] == "http://docs.example.com/external_api/v1.0/documents/"


def test_create_document_sends_bearer_token(docs_client):
    """create_document sends the OIDC token as a Bearer Authorization header."""
    session = {"oidc_access_token": "bearer-xyz"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc"}

    with patch("requests.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="Title", content="body", session=session)

    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer bearer-xyz"


def test_create_document_sends_markdown_file(docs_client):
    """create_document uploads the content as a .md file with text/markdown MIME type."""
    session = {"oidc_access_token": "tok"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc"}

    with patch("requests.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="My Doc", content="# Hello", session=session)

    files = mock_post.call_args.kwargs["files"]
    assert "file" in files
    filename, fileobj, mimetype = files["file"]
    assert filename == "My Doc.md"
    assert mimetype == "text/markdown"
    assert fileobj.read() == b"# Hello"


def test_create_document_uses_configured_timeout(docs_client):
    """create_document passes the configured timeout to requests.post."""
    session = {"oidc_access_token": "tok"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc"}

    with patch("requests.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="T", content="c", session=session)

    assert mock_post.call_args.kwargs["timeout"] == 10


def test_create_document_raises_on_http_error(docs_client):
    """create_document propagates HTTPError from raise_for_status."""
    session = {"oidc_access_token": "tok"}
    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")

    with patch("requests.post", return_value=fake_response):
        with pytest.raises(requests.exceptions.HTTPError):
            docs_client.create_document(title="T", content="c", session=session)


def test_create_document_raises_when_no_oidc_token(docs_client):
    """create_document raises PermissionDenied when the session has no OIDC token."""
    with pytest.raises(PermissionDenied):
        docs_client.create_document(title="T", content="c", session={})
