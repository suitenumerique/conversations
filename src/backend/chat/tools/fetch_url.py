"""Tool to fetch content from a URL detected in the conversation."""

import logging
import random
import re

import httpx
import trafilatura
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from chat.ai_sdk_types import TextUIPart

logger = logging.getLogger(__name__)

# Regex pattern to detect URLs
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
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


def detect_url_in_conversation(conversation) -> bool:
    """
    Detect if an URL is present in the conversation messages.
    
    Args:
        conversation: The ChatConversation instance.
    
    Returns:
        bool: True if at least one URL is found in the conversation, False otherwise.
    """
    if not conversation:
        return []
    
    # Check ui_messages first (most recent, updated before agent call)
    if hasattr(conversation, 'ui_messages') and conversation.ui_messages:
        for message in conversation.ui_messages:
            if not message:
                continue
            text_content = _extract_text_from_message(message)
            if text_content and URL_PATTERN.search(text_content):
                logger.info("URL detected in ui_messages: %s", URL_PATTERN.findall(text_content))
                return list(set(URL_PATTERN.findall(text_content)))
    
    # Also check stored messages (conversation history)
    if hasattr(conversation, 'messages') and conversation.messages:
        for message in conversation.messages:
            if not message:
                continue
            text_content = _extract_text_from_message(message)
            if text_content and URL_PATTERN.search(text_content):
                logger.info("URL detected in messages: %s", URL_PATTERN.findall(text_content))
                return list(set(URL_PATTERN.findall(text_content)))
    
    return []


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
    conversation = getattr(getattr(ctx, "deps", None), "conversation", None)
    urls = detect_url_in_conversation(conversation)

    if url not in urls:
        return ToolReturn(
            return_value={"url": url, "error": "URL not detected in conversation"},
            content=f"URL {url} not detected in conversation",
        )

    try:
        # Special handling for docs.numerique.gouv.fr
        if "docs.numerique.gouv.fr" in url and "/docs/" in url:
            # Use regex to extract the document ID
            m = re.search(r'docs/([^/]+)', url)
            if m:
                docs_id = m.group(1)
                url_transformed = f"https://docs.numerique.gouv.fr/api/v1.0/documents/{docs_id}/content/?content_format=markdown"
                
                try:
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        response = await _get_with_retry(client, url_transformed)
                        data = response.json()
                        content = data.get('content', '')
                        
                        if not content:
                            return ToolReturn(
                                return_value={"url": url, "error": "Content empty or private"},
                                content="Ce document Docs n'est pas public ou est vide."
                            )
                            
                        return ToolReturn(
                            return_value={
                                "url": url,
                                "original_url": url,
                                "content": content[:20000],  # Limit content
                                "source": "docs.numerique.gouv.fr"
                            }
                        )
                except Exception as e:
                    logger.warning("Error fetching Docs content %s: %s", url, e)
                    return ToolReturn(
                        return_value={"url": url, "error": str(e)},
                        content="Ce document Docs n'est pas public ou une erreur est survenue."
                    )

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await _get_with_retry(client, url)
            content = trafilatura.extract(response.text)
            
            return ToolReturn(
                return_value={
                    "url": url,
                    "status_code": response.status_code,
                    "content": content[:20000],  # Limit content to first 20000 chars
                    "content_type": response.headers.get("content-type", "unknown"),
                }
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

