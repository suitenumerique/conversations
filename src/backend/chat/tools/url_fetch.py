"""URL fetch tool for the conversation agent."""

import asyncio
import ipaddress
import logging
import re
import uuid
from io import BytesIO
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string

import httpx
from asgiref.sync import sync_to_async
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from trafilatura import extract

from chat import models
from chat.tools.descriptions import URL_FETCH_SYSTEM_PROMPT, URL_FETCH_TOOL_DESCRIPTION
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail

logger = logging.getLogger(__name__)

# Regex: match http(s):// followed by non-whitespace characters
_URL_PATTERN = re.compile(r"https?://\S+")
# Strip trailing punctuation that is likely sentence punctuation, not part of the URL
_TRAILING_PUNCTUATION = re.compile(r"[.,;:!?\"'`\]})>]+$")


def detect_urls(text: str) -> list[str]:
    """Extract all HTTP/HTTPS URLs from a string, stripping trailing punctuation."""
    return [_TRAILING_PUNCTUATION.sub("", u) for u in _URL_PATTERN.findall(text)]


def _is_private_address(hostname: str) -> bool:
    """Return True if hostname is a private/link-local/loopback IP address."""
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        # Not a bare IP address (it's a domain name) — let it through
        # DNS resolution is not performed here to avoid blocking on DNS
        return False


def is_url_allowed(url: str) -> bool:
    """Return True if the URL passes all security filters."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if not parsed.scheme or not parsed.netloc:
        return False

    hostname = parsed.hostname or ""
    blocked = (
        parsed.scheme in settings.URL_FETCH_BLOCKED_SCHEMES
        or hostname in settings.URL_FETCH_BLOCKED_HOSTS
        or _is_private_address(hostname)
        or any(hostname.endswith(tld) for tld in settings.URL_FETCH_BLOCKED_TLDS)
    )
    return not blocked


def _get_last_user_text(ctx: RunContext) -> str:
    """Extract the text of the latest user message from RunContext messages."""
    for msg in reversed(ctx.messages):
        if msg.kind == "request":
            for part in msg.parts:
                if part.part_kind == "user-prompt":
                    content = part.content
                    if isinstance(content, str):
                        return content
                    parts = []
                    for item in content:
                        if isinstance(item, str):
                            parts.append(item)
                        elif hasattr(item, "text"):
                            parts.append(item.text)
                    return " ".join(filter(None, parts))
    return ""


async def _ensure_collection(conversation, document_store_backend) -> object:
    """Return a document store instance, creating the collection if needed."""
    document_store = document_store_backend(conversation.collection_id)
    if not document_store.collection_id:
        collection_id = await document_store.acreate_collection(
            name=f"conversation-{conversation.pk}"
        )
        conversation.collection_id = str(collection_id)
        await conversation.asave(update_fields=["collection_id", "updated_at"])
        document_store = document_store_backend(conversation.collection_id)
    return document_store


async def _fetch_url(url: str) -> httpx.Response:
    """Fetch a URL with SSRF-safe redirect handling; raises ModelCannotRetry/ModelRetry on error."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            resp = await client.get(url)
            if resp.is_redirect:
                redirect_url = resp.headers.get("location", "")
                if not is_url_allowed(redirect_url):
                    raise ModelCannotRetry(
                        f"The URL {url} redirects to a location that is not allowed "
                        "for security reasons."
                    )
                resp = await client.get(redirect_url, follow_redirects=False)
                if resp.is_redirect:
                    raise ModelCannotRetry(f"Too many redirects for {url}.")
            resp.raise_for_status()
            return resp
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            logger.warning("URL requires authentication: %s (HTTP %s)", url, status)
            raise ModelCannotRetry(
                f"The page at {url} requires authentication. I cannot access it."
            ) from exc
        if status == 404:
            logger.warning("URL not found: %s (HTTP 404)", url)
            raise ModelCannotRetry(f"The page at {url} was not found (404).") from exc
        if status >= 500:
            logger.warning("Server error fetching %s (HTTP %s)", url, status)
            raise ModelRetry(
                f"The server at {url} returned an error ({status}). Retrying..."
            ) from exc
        raise ModelCannotRetry(f"Failed to access {url} (HTTP {status}).") from exc
    except httpx.TimeoutException as exc:
        logger.warning("Timeout fetching %s", url)
        raise ModelRetry(f"Request to {url} timed out. Retrying...") from exc
    except httpx.HTTPError as exc:
        logger.warning("HTTP error fetching %s: %s", url, type(exc).__name__)
        raise ModelRetry(
            f"Network error accessing {url}: {type(exc).__name__}. Retrying..."
        ) from exc


async def _store_html_content(  # noqa: PLR0913
    url: str, extracted: str, conversation, user, session: dict, document_store
) -> None:
    """Save extracted text as a text/plain attachment and index it in the RAG store."""
    content_bytes = extracted.encode("utf-8")
    key = f"{conversation.pk}/attachments/url-{uuid.uuid4()}.txt"
    await asyncio.to_thread(default_storage.save, key, BytesIO(content_bytes))
    await models.ChatConversationAttachment.objects.acreate(
        conversation=conversation,
        uploaded_by=user,
        key=key,
        file_name=url[:255],
        content_type="text/plain",
        size=len(content_bytes),
        upload_state=models.AttachmentStatus.READY,
    )
    await document_store.astore_document(url, extracted, user_sub=user.sub, session=session)


async def _store_pdf_content(  # noqa: PLR0913
    url: str, content: bytes, conversation, user, session: dict, document_store
) -> None:
    """Save PDF as attachment, parse and index it, and create a markdown attachment."""
    pdf_key = f"{conversation.pk}/attachments/url-{uuid.uuid4()}.pdf"
    await asyncio.to_thread(default_storage.save, pdf_key, BytesIO(content))
    await models.ChatConversationAttachment.objects.acreate(
        conversation=conversation,
        uploaded_by=user,
        key=pdf_key,
        file_name=url[:255],
        content_type="application/pdf",
        size=len(content),
        upload_state=models.AttachmentStatus.READY,
    )
    parsed_content = await asyncio.to_thread(
        document_store.parse_and_store_document,
        name=url,
        content_type="application/pdf",
        content=content,
        user_sub=user.sub,
        session=session,
    )
    if parsed_content:
        md_key = f"{conversation.pk}/attachments/url-{uuid.uuid4()}.md"
        md_bytes = parsed_content.encode("utf-8")
        await asyncio.to_thread(default_storage.save, md_key, BytesIO(md_bytes))
        await models.ChatConversationAttachment.objects.acreate(
            conversation=conversation,
            uploaded_by=user,
            key=md_key,
            file_name=f"{url}.md"[:255],
            content_type="text/markdown",
            size=len(md_bytes),
            conversion_from=pdf_key,
            upload_state=models.AttachmentStatus.READY,
        )


def add_url_fetch_tool(agent: Agent) -> None:
    """Register the url_fetch tool and its instructions hint on the given agent."""

    @agent.tool(
        name="url_fetch",
        retries=1,
        description=URL_FETCH_TOOL_DESCRIPTION,
    )
    @last_model_retry_soft_fail
    async def url_fetch(ctx: RunContext, url: str) -> ToolReturn:
        """
        Args:
            ctx (RunContext): The run context containing the conversation.
            url (str): The URL to fetch and index.
        """
        logger.debug("Fetching URL: %s", url)

        if not is_url_allowed(url):
            raise ModelCannotRetry(f"This URL is not allowed for security reasons ({url}).")

        resp = await _fetch_url(url)
        mime = resp.headers.get("content-type", "").split(";")[0].strip()

        supported_text = {"text/html", "text/plain"}
        supported_pdf = {"application/pdf"}
        if mime not in supported_text | supported_pdf:
            raise ModelCannotRetry(
                f"The link points to a {mime} file. I cannot analyse this type of content yet."
            )

        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
        conversation = ctx.deps.conversation
        user = ctx.deps.user
        session = ctx.deps.session
        document_store = await _ensure_collection(conversation, document_store_backend)

        if mime in supported_text:
            extracted = await sync_to_async(extract)(
                resp.text, include_comments=False, no_fallback=True
            )
            if not extracted:
                logger.warning("Empty extraction from %s (JS-rendered or auth-protected)", url)
                raise ModelCannotRetry(
                    f"The page at {url} did not return readable content. "
                    "It may require authentication or be a JavaScript-rendered page."
                )
            await _store_html_content(url, extracted, conversation, user, session, document_store)
        else:
            await _store_pdf_content(url, resp.content, conversation, user, session, document_store)

        return ToolReturn(return_value=f"Content from {url} has been indexed successfully.")

    @agent.instructions
    def url_fetch_instructions(ctx: RunContext) -> str:
        """Inject URL hint when the latest user message contains allowed URLs."""
        text = _get_last_user_text(ctx)
        if not text:
            return ""
        allowed = [u for u in detect_urls(text) if is_url_allowed(u)]
        if not allowed:
            return ""
        url_list = ", ".join(allowed)
        return URL_FETCH_SYSTEM_PROMPT.format(urls=url_list)
