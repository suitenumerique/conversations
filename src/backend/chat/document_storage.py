"""
Utilities for storing documents in RAG backend and creating attachments.

This module provides shared functionality for processing documents and storing them
in the RAG backend, as well as creating markdown attachments for non-text documents.
"""

import logging
from io import BytesIO
from typing import Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string
from django.utils.text import slugify

from chat import models

logger = logging.getLogger(__name__)


async def ensure_collection_exists(conversation) -> None:
    """
    Ensure that a document collection exists for the conversation.
    
    Creates a new collection if one doesn't exist and updates the conversation.
    
    Args:
        conversation: The ChatConversation instance.
    """
    document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
    document_store = document_store_backend(conversation.collection_id)
    
    if not document_store.collection_id:
        collection_id = document_store.create_collection(
            name=f"conversation-{conversation.pk}",
        )
        conversation.collection_id = str(collection_id)
        await conversation.asave(update_fields=["collection_id", "updated_at"])


async def store_document_in_rag(
    conversation,
    name: str,
    content_type: str,
    content: bytes | BytesIO,
    store_name: Optional[str] = None,
) -> str:
    """
    Parse and store a document in the RAG backend.
    
    Args:
        conversation: The ChatConversation instance.
        name: The name/identifier to use for parsing (should be filesystem-safe).
        content_type: The MIME type of the document.
        content: The document content as bytes or BytesIO.
        store_name: Optional name to use for storing (for metadata/citations).
                   If None, uses `name`.
    
    Returns:
        str: The parsed markdown content.
    """
    await ensure_collection_exists(conversation)
    
    document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
    document_store = document_store_backend(conversation.collection_id)
    
    # Normalize content to bytes first, then create a fresh BytesIO
    # The backend expects BytesIO in its signature, but internally passes it directly
    # to convert_raw which expects bytes. We ensure content is always bytes first,
    # then create a fresh BytesIO for the backend (which it needs for PDFs).
    if isinstance(content, BytesIO):
        # Read the BytesIO content to bytes
        content_bytes = content.read()
        # Reset position if possible (though we create a new BytesIO anyway)
        content.seek(0) if hasattr(content, 'seek') else None
    elif isinstance(content, bytes):
        content_bytes = content
    else:
        raise TypeError(f"content must be bytes or BytesIO, got {type(content)}")
    
    # Create a fresh BytesIO from the bytes for the backend
    # The backend needs BytesIO for PDFs (file-like object), but will pass it
    # directly to convert_raw for non-PDFs (which expects bytes).
    # This is a limitation of the backend that we can't fix.
    content_io = BytesIO(content_bytes)
    
    # Parse the document
    parsed_content = document_store.parse_document(
        name=name,
        content_type=content_type,
        content=content_io,
    )
    
    # Store the document (use store_name if provided, otherwise use name)
    document_store.store_document(
        name=store_name or name,
        content=parsed_content,
    )
    
    return parsed_content


async def create_markdown_attachment(
    conversation,
    user,
    file_name: str,
    parsed_content: str,
    key: Optional[str] = None,
    conversion_from: Optional[str] = None,
) -> models.ChatConversationAttachment:
    """
    Create a markdown attachment for a parsed document.
    
    Args:
        conversation: The ChatConversation instance.
        user: The user who uploaded/created the document.
        file_name: The name of the markdown file to create.
        parsed_content: The markdown content to store.
        key: Optional storage key. If None, generates from conversation.pk and file_name.
        conversion_from: Optional key of the original file if this is a conversion.
    
    Returns:
        ChatConversationAttachment: The created attachment instance.
    """
    if key is None:
        key = f"{conversation.pk}/attachments/{file_name}"
    
    md_attachment = await models.ChatConversationAttachment.objects.acreate(
        conversation=conversation,
        uploaded_by=user,
        key=key,
        file_name=file_name,
        content_type="text/markdown",
        conversion_from=conversion_from,
    )
    try:
        default_storage.save(key, ContentFile(parsed_content.encode("utf8")))
        md_attachment.upload_state = models.AttachmentStatus.READY
        await md_attachment.asave(update_fields=["upload_state", "updated_at"])
    except Exception as exc:
        logger.error("Failed to save markdown attachment to storage: %s", exc)
        await md_attachment.adelete()
        raise
    
    return md_attachment


async def store_document_with_attachment(
    conversation,
    user,
    name: str,
    content_type: str,
    content: bytes | BytesIO,
    store_name: Optional[str] = None,
    create_attachment: bool = True,
    conversion_from: Optional[str] = None,
    attachment_key: Optional[str] = None,
) -> tuple[str, Optional[models.ChatConversationAttachment]]:
    """
    Store a document in RAG and optionally create a markdown attachment.
    
    This is a convenience function that combines store_document_in_rag and
    create_markdown_attachment. It handles the common workflow of storing
    non-text documents.
    
    Args:
        conversation: The ChatConversation instance.
        user: The user who uploaded/created the document.
        name: The name/identifier to use for parsing (should be filesystem-safe).
        content_type: The MIME type of the document.
        content: The document content as bytes or BytesIO.
        store_name: Optional name to use for storing (for metadata/citations).
                   If None, uses `name`.
        create_attachment: Whether to create a markdown attachment.
                          Defaults to True for non-text content types.
        conversion_from: Optional key of the original file if this is a conversion.
        attachment_key: Optional custom key for the attachment. If None, generates
                        from conversation.pk and file_name.
    
    Returns:
        tuple[str, Optional[ChatConversationAttachment]]: The parsed content and
            the created attachment (if created).
    """
    parsed_content = await store_document_in_rag(
        conversation=conversation,
        name=name,
        content_type=content_type,
        content=content,
        store_name=store_name,
    )
    
    attachment = None
    if create_attachment and not content_type.startswith("text/"):
        file_name = f"{name}.md"
        attachment = await create_markdown_attachment(
            conversation=conversation,
            user=user,
            file_name=file_name,
            parsed_content=parsed_content,
            key=attachment_key,
            conversion_from=conversion_from,
        )
    
    return parsed_content, attachment

