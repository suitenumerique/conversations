"""Implementation of the La Suite Docs External API."""

import dataclasses
import logging
import re
import uuid
from datetime import datetime
from enum import StrEnum
from io import BytesIO
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils.dateparse import parse_datetime

import httpx
from asgiref.sync import sync_to_async

from core import instrumentation

logger = logging.getLogger(__name__)

# Candidate URLs in free text; trailing punctuation is stripped afterwards.
# Brackets, parentheses and commas end a candidate so that markdown links like
# [url](url) and comma-separated links split into separate URLs.
_URL_CANDIDATE_RE = re.compile(r"https?://[^\s<>\"'`\[\](),]+", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?)]}*_"


class DocsFetchFailure(StrEnum):
    """Coarse reason a Docs document could not be read."""

    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    TOO_LARGE = "too_large"


class DocsFetchError(Exception):
    """Raised when a Docs document cannot be read, carrying the coarse reason."""

    def __init__(self, reason: DocsFetchFailure):
        super().__init__(reason)
        self.reason = reason


@dataclasses.dataclass(frozen=True)
class DocsDocument:
    """Markdown content of a Docs document."""

    title: str
    content: str
    updated_at: datetime | None


def safe_file_stem(title: str) -> str:
    """Strip path separators and control characters so the title is a safe filename."""
    return re.sub(r"[/\\\x00-\x1f]", " ", title or "").strip() or "document"


def docs_document_url(document_id: uuid.UUID) -> str:
    """Return the browser URL of a Docs document."""
    return urljoin(settings.DOCS_BASE_URL, f"docs/{document_id}/")


def _parse_canonical_uuid(value: str) -> uuid.UUID | None:
    """Parse a UUID only in its canonical hyphenated form."""
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value.lower() else None


def _url_origin(parsed_url) -> tuple[str, str | None, int | None] | None:
    """Return the (scheme, host, port) of a parsed URL, or None if its port is invalid."""
    try:
        port = parsed_url.port
    except ValueError:
        return None
    return parsed_url.scheme.lower(), parsed_url.hostname, port


def extract_docs_document_ids(text: str, limit: int) -> list[uuid.UUID]:
    """Return the ids of the Docs documents linked in ``text``, deduplicated, at most ``limit``.

    A Docs link has the scheme and host of ``DOCS_BASE_URL`` and a ``docs/<uuid>/``
    path under it. Query strings and fragments are ignored.
    """
    docs_base_url = urlparse(urljoin(settings.DOCS_BASE_URL, "docs/"))
    docs_origin = _url_origin(docs_base_url)
    document_path_re = re.compile(
        rf"^{re.escape(docs_base_url.path)}(?P<document_id>[^/]+)/?$", re.IGNORECASE
    )

    document_ids: list[uuid.UUID] = []
    for candidate in _URL_CANDIDATE_RE.findall(text):
        parsed_url = urlparse(candidate.rstrip(_URL_TRAILING_PUNCTUATION))
        if _url_origin(parsed_url) != docs_origin:
            continue
        if not (match := document_path_re.match(parsed_url.path)):
            continue
        document_id = _parse_canonical_uuid(match.group("document_id"))
        if document_id is not None and document_id not in document_ids:
            document_ids.append(document_id)

    if len(document_ids) > limit:
        logger.info(
            "Ignoring %d Docs link(s) over the per-message limit of %d",
            len(document_ids) - limit,
            limit,
        )
    return document_ids[:limit]


def _fetch_failure_from_status(docs_status: int) -> DocsFetchFailure:
    """Map the HTTP status returned by Docs to a coarse failure reason."""
    # Docs answers 400 when the token belongs to an ended identity provider session.
    if docs_status in (httpx.codes.UNAUTHORIZED, httpx.codes.BAD_REQUEST):
        logger.warning("Docs rejected the access token while reading a document (%s)", docs_status)
        return DocsFetchFailure.UNAUTHENTICATED
    if docs_status == httpx.codes.FORBIDDEN:
        # Also returned for every action missing from Docs' EXTERNAL_API setting.
        logger.warning(
            "Docs denied access while reading a document (403); check that "
            "'formatted_content' is allowed in Docs' EXTERNAL_API documents actions"
        )
        return DocsFetchFailure.FORBIDDEN
    if docs_status == httpx.codes.NOT_FOUND:
        return DocsFetchFailure.NOT_FOUND
    logger.error("Docs returned an error while reading a document (%s)", docs_status)
    return DocsFetchFailure.UNAVAILABLE


class DocsClient:
    """
    Client for interacting with the La Suite Docs External API.
    It provides methods to:
        - Create a new document in Docs
        - Read a document as markdown
        - ... more methods can be added here as needed.
    """

    def __init__(self):
        """Initialize the DocsClient with necessary configuration.
        The API URL and timeout are set based on Django settings."""
        self.timeout = settings.DOCS_API_TIMEOUT
        self.api_url = urljoin(settings.DOCS_BASE_URL, "external_api/v1.0/")

    def get_access_token(self, session):
        """Retrieve the OIDC access token from the user's session."""
        access_token = session.get("oidc_access_token")
        if not access_token:
            raise PermissionDenied("User is not authenticated with OIDC.")
        return access_token

    def create_document(self, title: str, content: str, session) -> dict:
        """
        POST /external_api/v1.0/documents/ with markdown file upload (multipart).
        """
        access_token = self.get_access_token(session)
        file = BytesIO(content.encode("utf-8"))
        file.name = f"{safe_file_stem(title)}.md"
        with instrumentation.outgoing_request("docs", "create_document") as observed:
            response = httpx.post(
                urljoin(self.api_url, "documents/"),
                headers={"Authorization": f"Bearer {access_token}"},
                files={"file": (file.name, file, "text/markdown")},
                timeout=self.timeout,
            )
            observed.status = response.status_code
            response.raise_for_status()
        return response.json()

    async def fetch_document_markdown(self, document_id: uuid.UUID, session) -> DocsDocument:
        """
        GET /external_api/v1.0/documents/{id}/formatted-content/?content_format=markdown.

        Raises:
            PermissionDenied: the session holds no OIDC access token.
            DocsFetchError: Docs refused the request or could not be reached.
        """
        # The session may be lazily loaded from the database.
        access_token = await sync_to_async(self.get_access_token)(session)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    urljoin(self.api_url, f"documents/{document_id}/formatted-content/"),
                    params={"content_format": "markdown"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DocsFetchError(_fetch_failure_from_status(exc.response.status_code)) from exc
        except httpx.RequestError as exc:
            logger.warning("Docs unreachable while reading a document: %s", exc)
            raise DocsFetchError(DocsFetchFailure.UNAVAILABLE) from exc

        # A proxy in front of Docs may answer 200 with a login page instead of JSON.
        try:
            data = response.json()
            title = data.get("title") or ""
            content = data.get("content") or ""
            if not isinstance(title, str) or not isinstance(content, str):
                raise TypeError("Docs document title and content must be strings")
            return DocsDocument(
                title=title,
                content=content,
                updated_at=parse_datetime(data["updated_at"]) if data.get("updated_at") else None,
            )
        except ValueError, TypeError, AttributeError:
            logger.exception("Docs returned an unexpected response while reading a document")
            raise DocsFetchError(DocsFetchFailure.UNAVAILABLE) from None
