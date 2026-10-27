"""Tests for the DocsClient."""

import uuid
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied

import httpx
import pytest
import respx

from chat.docs_client import (
    DocsClient,
    DocsDocument,
    DocsFetchError,
    DocsFetchFailure,
    extract_docs_document_ids,
)

DOCUMENT_ID = uuid.UUID("0b8f1e9a-3c5d-4e2f-9a1b-7c6d5e4f3a21")
FORMATTED_CONTENT_URL = (
    f"http://docs.example.com/external_api/v1.0/documents/{DOCUMENT_ID}/formatted-content/"
    "?content_format=markdown"
)


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

    with patch("httpx.post", return_value=fake_response) as mock_post:
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

    with patch("httpx.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="Title", content="body", session=session)

    call_args = mock_post.call_args
    assert call_args.args[0] == "http://docs.example.com/external_api/v1.0/documents/"


def test_create_document_sends_bearer_token(docs_client):
    """create_document sends the OIDC token as a Bearer Authorization header."""
    session = {"oidc_access_token": "bearer-xyz"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc"}

    with patch("httpx.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="Title", content="body", session=session)

    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer bearer-xyz"


def test_create_document_sends_markdown_file(docs_client):
    """create_document uploads the content as a .md file with text/markdown MIME type."""
    session = {"oidc_access_token": "tok"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc"}

    with patch("httpx.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="My Doc", content="# Hello", session=session)

    files = mock_post.call_args.kwargs["files"]
    assert "file" in files
    filename, fileobj, mimetype = files["file"]
    assert filename == "My Doc.md"
    assert mimetype == "text/markdown"
    assert fileobj.read() == b"# Hello"


def test_create_document_uses_configured_timeout(docs_client):
    """create_document passes the configured timeout to httpx.post."""
    session = {"oidc_access_token": "tok"}
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "doc-abc"}

    with patch("httpx.post", return_value=fake_response) as mock_post:
        docs_client.create_document(title="T", content="c", session=session)

    assert mock_post.call_args.kwargs["timeout"] == 10


def test_create_document_raises_on_http_error(docs_client):
    """create_document propagates HTTPError from raise_for_status."""
    session = {"oidc_access_token": "tok"}
    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403 Forbidden", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.post", return_value=fake_response):
        with pytest.raises(httpx.HTTPStatusError):
            docs_client.create_document(title="T", content="c", session=session)


def test_create_document_raises_when_no_oidc_token(docs_client):
    """create_document raises PermissionDenied when the session has no OIDC token."""
    with pytest.raises(PermissionDenied):
        docs_client.create_document(title="T", content="c", session={})


# ---------------------------------------------------------------------------
# extract_docs_document_ids
# ---------------------------------------------------------------------------


@pytest.fixture(name="docs_https_base_url")
def docs_https_base_url_fixture(settings):
    """Point the Docs integration at an HTTPS instance."""
    settings.DOCS_BASE_URL = "https://docs.example.com/"


def _uuids(count):
    """Return ``count`` distinct canonical UUIDs."""
    return [uuid.UUID(int=index + 1, version=4) for index in range(count)]


def test_extract_docs_document_ids_valid_link(docs_https_base_url):  # pylint: disable=unused-argument
    """A link to a document on the Docs instance yields its id."""
    text = f"Please read https://docs.example.com/docs/{DOCUMENT_ID}/ and summarize."
    assert extract_docs_document_ids(text, limit=5) == [DOCUMENT_ID]


def test_extract_docs_document_ids_without_trailing_slash(docs_https_base_url):  # pylint: disable=unused-argument
    """The trailing slash of the document path is optional."""
    text = f"See https://docs.example.com/docs/{DOCUMENT_ID}."
    assert extract_docs_document_ids(text, limit=5) == [DOCUMENT_ID]


def test_extract_docs_document_ids_markdown_link(docs_https_base_url):  # pylint: disable=unused-argument
    """Trailing markdown punctuation around the URL is ignored."""
    text = f"[my doc](https://docs.example.com/docs/{DOCUMENT_ID}/)"
    assert extract_docs_document_ids(text, limit=5) == [DOCUMENT_ID]


@pytest.mark.parametrize(
    "template",
    [
        "[{first}]({second})",
        "{first},{second}",
    ],
)
def test_extract_docs_document_ids_adjacent_links(docs_https_base_url, template):  # pylint: disable=unused-argument
    """Links joined by markdown brackets or a comma are read as separate links."""
    first_id, second_id = _uuids(2)
    text = template.format(
        first=f"https://docs.example.com/docs/{first_id}/",
        second=f"https://docs.example.com/docs/{second_id}/",
    )
    assert extract_docs_document_ids(text, limit=5) == [first_id, second_id]


def test_extract_docs_document_ids_other_host(docs_https_base_url):  # pylint: disable=unused-argument
    """A link to another host is ignored."""
    text = f"https://evil.example.com/docs/{DOCUMENT_ID}/"
    assert not extract_docs_document_ids(text, limit=5)


def test_extract_docs_document_ids_subdomain_host(docs_https_base_url):  # pylint: disable=unused-argument
    """A host that only ends with the Docs host is ignored."""
    text = f"https://docs.example.com.evil.com/docs/{DOCUMENT_ID}/"
    assert not extract_docs_document_ids(text, limit=5)


def test_extract_docs_document_ids_scheme_mismatch(docs_https_base_url):  # pylint: disable=unused-argument
    """Same host over http while Docs is served over https is ignored."""
    text = f"http://docs.example.com/docs/{DOCUMENT_ID}/"
    assert not extract_docs_document_ids(text, limit=5)


def test_extract_docs_document_ids_non_docs_path(docs_https_base_url):  # pylint: disable=unused-argument
    """Same host but a path other than /docs/<uuid>/ is ignored."""
    text = (
        f"https://docs.example.com/templates/{DOCUMENT_ID}/ "
        f"https://docs.example.com/docs/{DOCUMENT_ID}/versions/"
    )
    assert not extract_docs_document_ids(text, limit=5)


def test_extract_docs_document_ids_unparsable_url(docs_https_base_url):  # pylint: disable=unused-argument
    """A URL that urlparse rejects is skipped without hiding the other links."""
    text = f"https://℀.example/docs/{DOCUMENT_ID}/ https://docs.example.com/docs/{DOCUMENT_ID}/"
    assert extract_docs_document_ids(text, limit=5) == [DOCUMENT_ID]


@pytest.mark.parametrize(
    "document_id",
    [
        "not-a-uuid",
        "0b8f1e9a3c5d4e2f9a1b7c6d5e4f3a21",  # not hyphenated
        "{0b8f1e9a-3c5d-4e2f-9a1b-7c6d5e4f3a21}",
        "0b8f1e9a-3c5d-4e2f-9a1b-7c6d5e4f3a2",  # too short
    ],
)
def test_extract_docs_document_ids_invalid_uuid(docs_https_base_url, document_id):  # pylint: disable=unused-argument
    """Only canonical UUIDs are accepted as document ids."""
    text = f"https://docs.example.com/docs/{document_id}/"
    assert not extract_docs_document_ids(text, limit=5)


def test_extract_docs_document_ids_deduplicates(docs_https_base_url):  # pylint: disable=unused-argument
    """The same document linked twice is returned once."""
    text = (
        f"https://docs.example.com/docs/{DOCUMENT_ID}/ and again "
        f"https://docs.example.com/docs/{str(DOCUMENT_ID).upper()}/?tab=1"
    )
    assert extract_docs_document_ids(text, limit=5) == [DOCUMENT_ID]


def test_extract_docs_document_ids_caps_at_limit(docs_https_base_url, caplog):  # pylint: disable=unused-argument
    """Links over the limit are ignored and logged, keeping the first ones."""
    document_ids = _uuids(6)
    text = " ".join(f"https://docs.example.com/docs/{document_id}/" for document_id in document_ids)

    assert extract_docs_document_ids(text, limit=5) == document_ids[:5]
    assert "Ignoring 1 Docs link(s) over the per-message limit of 5" in caplog.text


def test_extract_docs_document_ids_query_and_fragment(docs_https_base_url):  # pylint: disable=unused-argument
    """Query strings and fragments do not prevent the match."""
    text = f"https://docs.example.com/docs/{DOCUMENT_ID}/?utm_source=mail#heading-2"
    assert extract_docs_document_ids(text, limit=5) == [DOCUMENT_ID]


def test_extract_docs_document_ids_base_url_with_path(settings):
    """Docs served under a path prefix only matches links under that prefix."""
    settings.DOCS_BASE_URL = "https://example.com/impress/"
    text = (
        f"https://example.com/docs/{DOCUMENT_ID}/ https://example.com/impress/docs/{DOCUMENT_ID}/"
    )
    assert extract_docs_document_ids(text, limit=5) == [DOCUMENT_ID]


# ---------------------------------------------------------------------------
# fetch_document_markdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_fetch_document_markdown_success(docs_client):
    """The markdown and title of the document are returned."""
    route = respx.get(FORMATTED_CONTENT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": str(DOCUMENT_ID),
                "title": "My doc",
                "content": "# Hello",
                "created_at": "2026-10-01T10:00:00Z",
                "updated_at": "2026-10-02T12:30:00Z",
            },
        )
    )

    document = await docs_client.fetch_document_markdown(
        DOCUMENT_ID, {"oidc_access_token": "tok123"}
    )

    assert document == DocsDocument(title="My doc", content="# Hello")
    assert route.calls[0].request.headers["Authorization"] == "Bearer tok123"


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("docs_status", "reason"),
    [
        (400, DocsFetchFailure.UNAUTHENTICATED),
        (401, DocsFetchFailure.UNAUTHENTICATED),
        (403, DocsFetchFailure.FORBIDDEN),
        (404, DocsFetchFailure.NOT_FOUND),
        (500, DocsFetchFailure.UNAVAILABLE),
    ],
)
async def test_fetch_document_markdown_http_errors(docs_client, docs_status, reason):
    """Each HTTP error returned by Docs maps to a coarse reason."""
    respx.get(FORMATTED_CONTENT_URL).mock(return_value=httpx.Response(docs_status))

    with pytest.raises(DocsFetchError) as excinfo:
        await docs_client.fetch_document_markdown(DOCUMENT_ID, {"oidc_access_token": "tok"})

    assert excinfo.value.reason == reason


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>Sign in</html>"),
        httpx.Response(200, json=["not", "a", "document"]),
        httpx.Response(200, json={"title": "Doc", "content": {"blocks": []}}),
        httpx.Response(200, json={"title": 42, "content": "# Hello"}),
    ],
)
async def test_fetch_document_markdown_unexpected_response(docs_client, response):
    """A 200 that is not a document means Docs is unavailable."""
    respx.get(FORMATTED_CONTENT_URL).mock(return_value=response)

    with pytest.raises(DocsFetchError) as excinfo:
        await docs_client.fetch_document_markdown(DOCUMENT_ID, {"oidc_access_token": "tok"})

    assert excinfo.value.reason == DocsFetchFailure.UNAVAILABLE


@pytest.mark.asyncio
@respx.mock
async def test_fetch_document_markdown_timeout(docs_client):
    """A timeout reaching Docs means Docs is unavailable."""
    respx.get(FORMATTED_CONTENT_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(DocsFetchError) as excinfo:
        await docs_client.fetch_document_markdown(DOCUMENT_ID, {"oidc_access_token": "tok"})

    assert excinfo.value.reason == DocsFetchFailure.UNAVAILABLE


@pytest.mark.asyncio
@respx.mock
async def test_fetch_document_markdown_raises_when_no_oidc_token(docs_client):
    """Without an OIDC token, Docs is not called and PermissionDenied is raised."""
    route = respx.get(FORMATTED_CONTENT_URL)

    with pytest.raises(PermissionDenied):
        await docs_client.fetch_document_markdown(DOCUMENT_ID, {})

    assert not route.called
