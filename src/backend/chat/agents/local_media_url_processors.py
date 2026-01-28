"""
ImageUrl processors and utilities.

Allow to manage local image URLs in messages, replacing them with presigned S3 URLs
for the LLM to access them, and then reverting them back to local URLs when
storing the messages in the database.
"""

import base64
import logging
import mimetypes
import secrets
from typing import Dict, Iterable

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage

from pydantic_ai import DocumentUrl, ImageUrl, ModelMessage, ModelRequest, UserPromptPart

from core.file_upload.enums import FileToLLMMode
from core.file_upload.utils import generate_retrieve_policy

from chat.models import ChatConversation

logger = logging.getLogger(__name__)


def generate_temporary_url(key: str) -> str:
    """
    Generate a temporary URL for accessing a file through the backend.

    Instead of using S3 presigned URLs, this creates a temporary access key
    that's stored in cache (3 minutes TTL). The LLM accesses the file through
    a backend endpoint that validates the key and streams the file content.

    This approach:
    - Works even when S3 is not accessible from the LLM
    - Provides better security (key is time-limited and single-use)
    - Allows the backend to control file access centrally

    Args:
        key (str): The S3 object key where the file is stored.

    Returns:
        str: A temporary URL with format: /api/v1.0/file-stream/{temporary_key}/
    """
    # Generate a secure random key
    temporary_key = secrets.token_urlsafe(32)

    # Store the S3 key in cache
    cache_key = f"file_access:{temporary_key}"
    cache.set(cache_key, key, timeout=settings.FILE_BACKEND_TEMPORARY_URL_EXPIRATION)

    logger.info("Generated temporary file access key for S3 key: %s", key)

    # Return the URL that the LLM will use to access the file
    return f"{settings.FILE_BACKEND_URL}/api/v1.0/file-stream/{temporary_key}/"


def _get_file_url_for_llm(key: str, mode: str | None = None) -> str:
    """
    Get the appropriate URL for the LLM to access a file based on the upload mode.

    Args:
        key (str): The S3 object key where the file is stored.
        mode (str, optional): The upload mode. Defaults to FILE_TO_LLM_MODE setting.

    Returns:
        str: The URL or data URL for the LLM to use.

    Supported modes:
    - presigned_url: Returns a presigned S3 URL (default)
    - backend_temporary_url: Returns a presigned URL with shorter expiration
    - backend_base64: Returns a data URL with base64-encoded file content
    """
    if mode is None:
        mode = settings.FILE_TO_LLM_MODE

    if mode == FileToLLMMode.BACKEND_BASE64:
        # Read file from S3 and encode as base64 data URL
        try:
            with default_storage.open(key, "rb") as file:
                file_content = file.read()
                # Detect MIME type from file extension or default to octet-stream
                mime_type, _ = mimetypes.guess_type(key)
                if not mime_type:
                    mime_type = "application/octet-stream"

                # Create data URL
                b64_content = base64.b64encode(file_content).decode("utf-8")
                return f"data:{mime_type};base64,{b64_content}"
        except Exception:  # pylint: disable=broad-except
            # Fall back to presigned URL on error
            logger.exception(
                "Failed to read file for base64 encoding, falling back to presigned URL"
            )
            return generate_retrieve_policy(key)

    elif mode == FileToLLMMode.BACKEND_TEMPORARY_URL:
        return generate_temporary_url(key)

    # FileToLLMMode.PRESIGNED_URL or default
    return generate_retrieve_policy(key)


def update_local_urls(
    conversation: ChatConversation,
    contents: Iterable[ImageUrl | DocumentUrl],
    updated_url: Dict[str, str] | None = None,
) -> Iterable[ImageUrl | DocumentUrl]:
    """
    Replace local image or document URLs in the content list to use appropriate S3 URLs
    based on the configured FILE_TO_LLM_MODE.

    ⚠️Be careful, `media_contents` are replaced in place.

    Args:
        conversation (ChatConversation): The chat conversation object.
        contents (Iterable[ImageUrl | DocumentUrl]): Iterable of UserContent objects.
        updated_url (Dict[str, str], optional): Dictionary to store
            mapping of original URLs to updated URLs.
    Returns:
        Iterable[ImageUrl | DocumentUrl]: Updated iterable of UserContent objects
            with appropriate S3 URLs based on the configured mode.
    """
    # When images are stored locally, there is no host in the URL, so we can
    # just check if the URL starts, frontend adds a prefix `/media-key/` to the key.
    local_media_url_prefix = "/media-key/"
    local_media_url_prefix_len = len(local_media_url_prefix)

    # Filter only ImageUrl contents
    media_contents = (c for c in contents if isinstance(c, (ImageUrl, DocumentUrl)))

    # Replace URLs with appropriate S3 URLs based on mode
    upload_mode = settings.FILE_TO_LLM_MODE

    for content in media_contents:
        idx = content.url.find(local_media_url_prefix)

        if idx == 0:
            _initial_url = str(content.url)
            key = content.url[local_media_url_prefix_len:]

            # Security check: ensure the image belongs to the conversation, if yes,
            # the user had access to the endpoint, so they have access to the image.
            if not key.startswith(f"{conversation.pk}/"):
                # The LLM will throw an error when trying to access the image,
                # this is not perfect, but this should never happen in practice,
                # except if the user tampers with the conversation.
                continue

            content.url = _get_file_url_for_llm(key, upload_mode)
            if updated_url is not None:
                updated_url[content.url] = _initial_url

    return contents


def update_history_local_urls(
    conversation: ChatConversation, messages: list[ModelMessage]
) -> list[ModelMessage]:
    """
    Replace local image/documents URLs in the message list to use appropriate S3 URLs.

    ⚠️Be careful, `messages` are replaced in place.

    We don't need to store the mapping of updated URLs to original URLs here because
    this function is used when sending the history to the LLM (which is already stored
    in the database with local URLs).

    Args:
        messages (list[ModelMessage]): List of ModelMessage objects.
    Returns:
        list[ModelMessage]: Updated list of ModelMessage objects with appropriate S3 URLs.
    """
    # Filter only ModelRequest messages
    requests = (msg for msg in messages if isinstance(msg, ModelRequest))

    for message in requests:
        # Filter only UserPromptPart parts
        user_parts = (part for part in message.parts if isinstance(part, UserPromptPart))

        for part in user_parts:
            update_local_urls(conversation, part.content)

    return messages
