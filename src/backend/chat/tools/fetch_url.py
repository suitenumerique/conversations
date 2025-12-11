"""Tool to fetch content from a URL detected in the conversation."""

import logging
import random
import re

import httpx
from django.conf import settings
from django.utils.text import slugify
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
import trafilatura

from chat import models
from chat.ai_sdk_types import TextUIPart
from chat.document_storage import (
    create_markdown_attachment,
    ensure_collection_exists,
    store_document_in_rag,
)

logger = logging.getLogger(__name__)

MAX_INLINE_CONTENT_CHARS = 8000

# Host for Docs.numerique.gouv.fr
DOCS_HOST = "docs.numerique.gouv.fr"

# Regex pattern to detect URLs
# Note: This is a permissive pattern for detection in free text, not strict validation
URL_PATTERN = re.compile(
    r'https?://(?:[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]|(?:%[0-9a-fA-F]{2}))+'
)

def _get_headers() -> dict:
    """
    Return a random set of HTTP headers for each request.

    For now this only randomizes the User-Agent, but we can easily extend this
    list with more header variants (Accept-Language, Referer, etc.) if needed.
    """
    headers_pool = [
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.1 Safari/605.1.15"
            )
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) "
                "Gecko/20100101 Firefox/121.0"
            )
        },
    ]

    return random.choice(headers_pool)

def _extract_text_from_message(message) -> str:
    """
    Extract all text content from a message.
    
    Args:
        message: A message object (UIMessage or dict).
    
    Returns:
        str: All text content concatenated.
    """
    text_parts = []
    
    # Handle UIMessage objects (Pydantic models)
    if hasattr(message, 'parts'):
        for part in message.parts or []:
            if isinstance(part, TextUIPart) and part.text:
                text_parts.append(part.text)
        # Also check the deprecated content field
        if hasattr(message, 'content') and message.content:
            text_parts.append(message.content)
    # Handle dict-based messages (JSON deserialized)
    elif isinstance(message, dict):
        # Check parts
        parts = message.get('parts', [])
        for part in parts:
            if isinstance(part, dict) and part.get('type') == 'text':
                text = part.get('text', '')
                if text:
                    text_parts.append(text)
        # Check deprecated content field
        content = message.get('content', '')
        if content:
            text_parts.append(content)
    
    return ' '.join(text_parts)


def detect_url_in_conversation(messages=None) -> list[str]:
    """
    Detect URLs present in the conversation messages.

    Args:
        messages: Iterable of UIMessage/dict messages (latest payload).

    Returns:
        list[str]: List of unique URLs found in the conversation.
    """
    found_urls = set()

    def extract_urls_from_messages(messages):
        if not messages:
            return
        for message in messages:
            if not message:
                continue
            text_content = _extract_text_from_message(message)
            if text_content and URL_PATTERN.search(text_content):
                matches = URL_PATTERN.findall(text_content)
                found_urls.update(matches)

    if messages:
        extract_urls_from_messages(messages)

    return list(found_urls)


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    max_attempts: int = 3,
) -> httpx.Response:
    """
    Perform a GET request with randomized headers and a simple retry strategy.

    We retry once on header-related HTTP status codes (e.g. 403, 429), each time
    using a new random header set. Other errors are propagated immediately.
    """
    last_exception: httpx.HTTPStatusError | None = None

    for attempt in range(max_attempts):
        headers = _get_headers()
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            last_exception = exc
            status_code = exc.response.status_code

            # Only retry on codes that are likely related to headers / rate limits.
            should_retry = status_code in (403, 429)
            is_last_attempt = attempt >= max_attempts - 1

            logger.debug(
                "HTTP error %s for URL %s on attempt %s with headers %s (retry=%s)",
                status_code,
                url,
                attempt + 1,
                headers,
                should_retry and not is_last_attempt,
            )

            if (not should_retry) or is_last_attempt:
                raise

    # Should not be reached, but keeps type-checkers happy.
    if last_exception is not None:
        raise last_exception

    raise RuntimeError("Unexpected state in _get_with_retry")


async def _store_in_rag_and_attachments(
    conversation,
    user,
    url: str,
    content_bytes: bytes,
    content_type: str,
) -> str:
    """
    Store the fetched document into the RAG backend and create a markdown attachment.

    Returns the markdown content stored, mainly to allow generating a short preview.
    """
    await ensure_collection_exists(conversation)

    # Force content_type to "application/pdf" if it seems to be a PDF but the header was weird
    # This ensures AlbertRagBackend uses the PDF parser
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        content_type = "application/pdf"

    # Use a safe filename (slugified) for the RAG backend to avoid API errors with URLs.
    # This is required because the Albert API (especially PDF parsing) does not handle
    # filenames with URL characters like "://" or "/" correctly.
    safe_rag_name = slugify(url)[:100] or "document"

    # We must split parsing and storing to handle the filename vs metadata issue:
    # 1. Parsing needs a safe filename (no slashes) to avoid 500 errors from the API.
    # 2. Storing needs the original URL in metadata so citations are correct.
    # However, AlbertRagBackend.store_document uses the same name for both filename and metadata.
    # We try to pass the original URL to store_document, hoping the storage endpoint is more
    # robust than the parser endpoint regarding filenames.
    parsed_content = await store_document_in_rag(
        conversation=conversation,
        name=safe_rag_name,
        content_type=content_type,
        content=content_bytes,
        store_name=url,
    )

    # Create a markdown attachment so that the rest of the pipeline
    # (document_search_rag, summarization, etc.) can see documents exist.
    file_name = f"{safe_rag_name}.md"
    key = f"{conversation.pk}/attachments/{file_name}"

    await create_markdown_attachment(
        conversation=conversation,
        user=user,
        file_name=file_name,
        parsed_content=parsed_content,
        key=key,
        # Keep track of the original URL so downstream tools (e.g. summarize)
        # can surface a clickable source instead of the slugified filename.
        conversion_from=url,
    )

    return parsed_content


async def fetch_url(ctx: RunContext, url: str) -> ToolReturn:
    """
    Fetch content from a URL.
    When an URL is detected and you need to fetch content from it, you should use this tool.
    
    Args:
        ctx (RunContext): The run context containing the conversation.
        url (str): The URL to fetch content from.
    
    Returns:
        ToolReturn: The fetched content from the URL.
    """
    # Access the Django conversation object from the agent dependencies
    deps = getattr(ctx, "deps", None)
    conversation = getattr(deps, "conversation", None)
    user = getattr(deps, "user", None)

    messages_for_detection = getattr(deps, "messages", None)
    urls = detect_url_in_conversation(messages_for_detection)
    logger.info("URLs authorized (extracted from messages): %s", urls)

    # If messages are provided, enforce URL presence; otherwise skip the check.
    if messages_for_detection is not None and url not in urls:
        return ToolReturn(
            return_value={"url": url, "error": "URL not detected in conversation", "content" : f"URL {url} not detected in conversation"},
        )

    try:
        # Special handling for docs.numerique.gouv.fr
        m = re.search(r"https?://(?:www\.)?docs\.numerique\.gouv\.fr/docs/([^/?#]+)", url)
        if m:
            docs_id = m.group(1)
            url_transformed = f"https://{DOCS_HOST}/api/v1.0/documents/{docs_id}/content/?content_format=markdown"
            
            try:
                async with httpx.AsyncClient(timeout=settings.FETCH_URL_TIMEOUT, follow_redirects=True) as client:
                    response = await _get_with_retry(client, url_transformed)
                    data = response.json()
                    content = data.get('content', '')
                    
                    if not content:
                        return ToolReturn(
                            return_value={"url": url, "error": "Content empty or private", "content": "Ce document Docs n'est pas public ou est vide."},
                        )
                    # If the Docs content is very large, route it through RAG instead of
                    # returning everything inline.
                    if conversation and user and len(content) > MAX_INLINE_CONTENT_CHARS:
                        parsed = await _store_in_rag_and_attachments(
                            conversation=conversation,
                            user=user,
                            url=url,
                            content_bytes=content.encode("utf-8"),
                            content_type="text/markdown",
                        )
                        preview = parsed[:MAX_INLINE_CONTENT_CHARS]
                        return ToolReturn(
                            return_value={
                                "url": url,
                                "original_url": url,
                                "stored_in_rag": True,
                                "content_preview": preview,
                                "source": DOCS_HOST,
                                "content":(
                                "Le contenu de ce document est volumineux et a été indexé dans "
                                "la base de documents de la conversation. "
                                "Pour l’interroger, tu dois utiliser l’outil `document_search_rag` "
                                "avec une requête précise décrivant ce que tu cherches dans ce document."
                            )
                            },
                            metadata={"sources": {url}},
                        )

                    return ToolReturn(
                        return_value={
                            "url": url,
                            "original_url": url,
                            "content": content[:MAX_INLINE_CONTENT_CHARS],
                            "source": DOCS_HOST,
                        }
                    )
            except Exception as e:
                logger.warning("Error fetching Docs content %s: %s", url, e)
                return ToolReturn(
                    return_value={"url": url, "error": str(e), "content": "Ce document Docs n'est pas public ou une erreur est survenue."},
                )

        async with httpx.AsyncClient(timeout=settings.FETCH_URL_TIMEOUT, follow_redirects=True) as client:
            response = await _get_with_retry(client, url)
            content_type_header = response.headers.get("content-type", "unknown")
            content_type = content_type_header.split(";", 1)[0].strip().lower()

            is_binary_like = not content_type.startswith("text/")
            is_pdf = "pdf" in content_type or url.lower().endswith(".pdf")

            # Avoid trafilatura on PDFs
            if is_pdf:
                extracted = ""
            else:
                extracted = trafilatura.extract(response.text) or response.text

            # For large or binary/PDF content, store in RAG instead of returning everything inline.
            if (
                conversation
                and user
                and (is_binary_like or is_pdf or len(extracted) > MAX_INLINE_CONTENT_CHARS)
            ):
                parsed = await _store_in_rag_and_attachments(
                    conversation=conversation,
                    user=user,
                    url=url,
                    content_bytes=response.content,
                    content_type=content_type,
                )
                preview = parsed[:MAX_INLINE_CONTENT_CHARS]
                return ToolReturn(
                    return_value={
                        "url": url,
                        "status_code": response.status_code,
                        "stored_in_rag": True,
                        "content_preview": preview,
                        "content_type": content_type_header,
                        "content":(
                        "Le contenu de cette ressource est volumineux ou de type fichier "
                        "(par exemple PDF). Il a été indexé dans la base de documents de la "
                        "conversation. Pour l’exploiter, tu dois utiliser l’outil "
                        "`document_search_rag` avec une requête précise décrivant les "
                        "informations que tu souhaites retrouver."
                    )
                    },
                    metadata={"sources": {url}},
                )

            # Small textual content: keep the existing behaviour with inline content.
            return ToolReturn(
                return_value={
                    "url": url,
                    "status_code": response.status_code,
                    "content": extracted[:MAX_INLINE_CONTENT_CHARS],
                    "content_type": content_type_header,
                },
                metadata={"sources": {url}},
            )
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        return ToolReturn(
            return_value={
                "url": url,
                "error": f"HTTP {e.response.status_code}: {str(e)}",
            }
        )
    except httpx.TimeoutException as e:
        logger.warning("Timeout fetching %s: %s", url, e)
        return ToolReturn(
            return_value={
                "url": url,
                "error": f"Timeout: {str(e)}",
            }
        )
    except Exception as e:
        logger.exception("Error fetching %s: %s", url, e)
        return ToolReturn(
            return_value={
                "url": url,
                "error": f"Error: {str(e)}",
            }
        )

