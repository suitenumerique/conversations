"""Tool to fetch content from a URL detected in the conversation."""

import logging
import re

import httpx
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from chat.ai_sdk_types import TextUIPart

logger = logging.getLogger(__name__)

# Regex pattern to detect URLs
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)


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
        return False
    
    # Check ui_messages first (most recent, updated before agent call)
    if hasattr(conversation, 'ui_messages') and conversation.ui_messages:
        for message in conversation.ui_messages:
            if not message:
                continue
            text_content = _extract_text_from_message(message)
            if text_content and URL_PATTERN.search(text_content):
                logger.debug("URL detected in ui_messages: %s", URL_PATTERN.findall(text_content))
                return True
    
    # Also check stored messages (conversation history)
    if hasattr(conversation, 'messages') and conversation.messages:
        for message in conversation.messages:
            if not message:
                continue
            text_content = _extract_text_from_message(message)
            if text_content and URL_PATTERN.search(text_content):
                logger.debug("URL detected in messages: %s", URL_PATTERN.findall(text_content))
                return True
    
    # Check pydantic_messages (conversation history in pydantic format)
    if hasattr(conversation, 'pydantic_messages') and conversation.pydantic_messages:
        for msg_data in conversation.pydantic_messages:
            if not msg_data:
                continue
            # pydantic_messages are stored as dict/JSON
            if isinstance(msg_data, dict):
                # Check parts in the message
                parts = msg_data.get('parts', [])
                for part in parts:
                    if isinstance(part, dict):
                        # Check for text content
                        content = part.get('content', '')
                        if content and URL_PATTERN.search(content):
                            logger.debug("URL detected in pydantic_messages: %s", URL_PATTERN.findall(content))
                            return True
    
    return False


async def fetch_url(ctx: RunContext, url: str) -> ToolReturn:
    """
    Fetch content from a URL.
    
    This tool is only available when an URL is detected in the conversation.
    The model should use this tool to fetch content from URLs mentioned in the conversation.
    
    Args:
        ctx (RunContext): The run context containing the conversation.
        url (str): The URL to fetch content from.
    
    Returns:
        ToolReturn: The fetched content from the URL.
    """
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
                        response = await client.get(url_transformed)
                        response.raise_for_status()
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
                            },
                            content=f"Contenu récupéré de Docs: {content[:500]}..."
                        )
                except Exception as e:
                    logger.warning("Error fetching Docs content %s: %s", url, e)
                    return ToolReturn(
                        return_value={"url": url, "error": str(e)},
                        content="Ce document Docs n'est pas public ou une erreur est survenue."
                    )

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.text
            
            return ToolReturn(
                return_value={
                    "url": url,
                    "status_code": response.status_code,
                    "content": content[:20000],  # Limit content to first 20000 chars
                    "content_type": response.headers.get("content-type", "unknown"),
                },
                content=f"Successfully fetched content from {url}",
            )
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        return ToolReturn(
            return_value={
                "url": url,
                "error": f"HTTP {e.response.status_code}: {str(e)}",
            },
            content=f"Failed to fetch {url}: HTTP {e.response.status_code}",
        )
    except httpx.TimeoutException as e:
        logger.warning("Timeout fetching %s: %s", url, e)
        return ToolReturn(
            return_value={
                "url": url,
                "error": f"Timeout: {str(e)}",
            },
            content=f"Timeout while fetching {url}",
        )
    except Exception as e:
        logger.exception("Error fetching %s: %s", url, e)
        return ToolReturn(
            return_value={
                "url": url,
                "error": f"Error: {str(e)}",
            },
            content=f"Error fetching {url}: {str(e)}",
        )

