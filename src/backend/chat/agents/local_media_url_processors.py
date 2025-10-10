"""
ImageUrl processors and utilities.

Allow to manage local image URLs in messages, replacing them with presigned S3 URLs
for the LLM to access them, and then reverting them back to local URLs when
storing the messages in the database.
"""

from typing import Dict, Iterable

from pydantic_ai import DocumentUrl, ImageUrl, ModelMessage, ModelRequest, UserPromptPart

from core.file_upload.utils import generate_retrieve_policy

from chat.models import ChatConversation


def update_local_urls(
    conversation: ChatConversation,
    contents: Iterable[ImageUrl | DocumentUrl],
    updated_url: Dict[str, str] | None = None,
) -> Iterable[ImageUrl | DocumentUrl]:
    """
    Replace local image or document URLs in the content list to use presigned S3 URLs.
    ⚠️Be careful, `media_contents` are replaced in place.

    Args:
        conversation (ChatConversation): The chat conversation object.
        contents (Iterable[ImageUrl | DocumentUrl]): Iterable of UserContent objects.
        updated_url (Dict[str, str], optional): Dictionary to store
            mapping of original URLs to updated URLs.
    Returns:
        Iterable[ImageUrl | DocumentUrl]: Updated iterable of UserContent objects
            with presigned URLs.
    """
    # When images are stored locally, there is no host in the URL, so we can
    # just check if the URL starts, frontend adds a prefix `/media-key/` to the key.
    local_media_url_prefix = "/media-key/"
    local_media_url_prefix_len = len(local_media_url_prefix)

    # Filter only ImageUrl contents
    media_contents = (c for c in contents if isinstance(c, (ImageUrl, DocumentUrl)))

    # Replace URLs with presigned URLs
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

            content.url = generate_retrieve_policy(key)
            if updated_url is not None:
                updated_url[content.url] = _initial_url

    return contents


def update_history_local_urls(
    conversation: ChatConversation, messages: list[ModelMessage]
) -> list[ModelMessage]:
    """
    Replace local image/documents URLs in the message list to use presigned S3 URLs.

    ⚠️Be careful, `messages` are replaced in place.

    We don't need to store the mapping of updated URLs to original URLs here because
    this function is used when sending the history to the LLM (which is already stored
    in the database with local URLs).

    Args:
        messages (list[ModelMessage]): List of ModelMessage objects.
    Returns:
        list[ModelMessage]: Updated list of ModelMessage objects with presigned URLs.
    """
    # Filter only ModelRequest messages
    requests = (msg for msg in messages if isinstance(msg, ModelRequest))

    for message in requests:
        # Filter only UserPromptPart parts
        user_parts = (part for part in message.parts if isinstance(part, UserPromptPart))

        for part in user_parts:
            update_local_urls(conversation, part.content)

    return messages
