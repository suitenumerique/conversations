"""Centralized collection lookup, creation, and re-indexing for conversations and projects."""

import logging
from io import BytesIO
from typing import Type

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string

from core.file_upload.enums import AttachmentStatus

from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend
from chat.agent_rag.document_rag_backends.registry import get_backend_key
from chat.models import ChatConversationAttachment, Collection, CollectionDocument

logger = logging.getLogger(__name__)


def _current_backend_key() -> str:
    return get_backend_key(settings.RAG_DOCUMENT_SEARCH_BACKEND)


def _default_backend_class() -> Type[BaseRagBackend]:
    return import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)


# ------------------------------------------------------------------ #
# Conversation - sync helpers
# ------------------------------------------------------------------ #


def get_conversation_collection(conversation):
    """Return the Collection for the current backend, or None."""

    return Collection.objects.filter(
        conversation=conversation,
        backend=_current_backend_key(),
    ).first()


def get_or_create_conversation_collection(conversation, backend_class=None):
    """Return (Collection, BaseRagBackend) for the current backend.

    Creates the external collection and DB row if they don't exist yet.
    ``backend_class`` can be injected for testability (defaults to settings).
    """

    backend_class = backend_class or _default_backend_class()
    current_key = _current_backend_key()

    collection = Collection.objects.filter(
        conversation=conversation,
        backend=current_key,
    ).first()

    if collection:
        return collection, backend_class(collection.external_id)

    backend = backend_class()
    external_id = backend.create_collection(name=f"conversation-{conversation.pk}")
    collection = Collection.objects.create(
        backend=current_key,
        external_id=str(external_id),
        name=f"conversation-{conversation.pk}",
        conversation=conversation,
    )
    return collection, backend


def reindex_collection(conversation, user_sub: str, backend_class=None):
    """Re-index all documents into a new collection on the current backend.

    Called when the configured RAG backend differs from the collection's backend
    (e.g. after switching from Albert to Find).

    Returns the newly created Collection.
    """

    collection, backend = get_or_create_conversation_collection(
        conversation,
        backend_class=backend_class,
    )

    attachments = ChatConversationAttachment.objects.filter(
        conversation=conversation,
        conversion_from__isnull=True,
    )

    for attachment in attachments:
        try:
            with default_storage.open(attachment.key, "rb") as f:
                content = f.read()
            backend.parse_and_store_document(
                name=attachment.file_name,
                content_type=attachment.content_type,
                content=content,
                user_sub=user_sub,
            )
            CollectionDocument.objects.create(
                collection=collection,
                attachment=attachment,
            )
        except Exception:
            logger.exception(
                "Failed to re-index attachment %s into collection %s",
                attachment.pk,
                collection.pk,
            )

    logger.info(
        "Re-indexed conversation %s to backend %s (collection %s)",
        conversation.pk,
        collection.backend,
        collection.pk,
    )
    return collection


# ------------------------------------------------------------------ #
# Conversation - async helpers
# ------------------------------------------------------------------ #


async def aget_conversation_collection(conversation):
    """Async variant of get_conversation_collection."""

    return await Collection.objects.filter(
        conversation=conversation,
        backend=_current_backend_key(),
    ).afirst()


async def aget_or_create_conversation_collection(conversation, backend_class=None):
    """Async variant of get_or_create_conversation_collection.

    Returns (Collection, BaseRagBackend).
    ``backend_class`` can be injected for testability (defaults to settings).
    """

    backend_class = backend_class or _default_backend_class()
    current_key = _current_backend_key()

    collection = await Collection.objects.filter(
        conversation=conversation,
        backend=current_key,
    ).afirst()

    if collection:
        return collection, backend_class(collection.external_id)

    backend = backend_class()
    external_id = await backend.acreate_collection(
        name=f"conversation-{conversation.pk}",
    )
    collection = await Collection.objects.acreate(
        backend=current_key,
        external_id=str(external_id),
        name=f"conversation-{conversation.pk}",
        conversation=conversation,
    )
    return collection, backend


# ------------------------------------------------------------------ #
# Project - sync helpers
# ------------------------------------------------------------------ #


def get_project_collection(project):
    """Return the project's Collection for the current backend, or None."""

    return Collection.objects.filter(
        project=project,
        backend=_current_backend_key(),
    ).first()


def get_or_create_project_collection(project, backend_class=None):
    """Return (Collection, BaseRagBackend) for the project on the current backend.

    Creates the external collection and DB row if they don't exist yet.
    """

    backend_class = backend_class or _default_backend_class()
    current_key = _current_backend_key()

    collection = Collection.objects.filter(
        project=project,
        backend=current_key,
    ).first()

    if collection:
        return collection, backend_class(collection.external_id)

    backend = backend_class()
    external_id = backend.create_collection(name=f"project-{project.pk}")
    collection = Collection.objects.create(
        backend=current_key,
        external_id=str(external_id),
        name=f"project-{project.pk}",
        project=project,
    )
    return collection, backend


def ensure_project_attachments_indexed(project, user_sub: str, backend_class=None):
    """Index any READY project attachments that are not yet in the current collection.

    Returns (Collection, BaseRagBackend) or (None, None) if there are no attachments.
    """

    ready_attachments = ChatConversationAttachment.objects.filter(
        project=project,
        upload_state=AttachmentStatus.READY,
        conversion_from__isnull=True,
    ).exclude(content_type__startswith="image/")
    if not ready_attachments.exists():
        return None, None

    collection, backend = get_or_create_project_collection(project, backend_class=backend_class)

    already_indexed = set(
        CollectionDocument.objects.filter(collection=collection)
        .values_list("attachment_id", flat=True)
    )

    for attachment in ready_attachments:
        if attachment.pk in already_indexed:
            continue
        try:
            with default_storage.open(attachment.key, "rb") as f:
                content = f.read()
            parsed_content = backend.parse_and_store_document(
                name=attachment.file_name,
                content_type=attachment.content_type,
                content=content,
                user_sub=user_sub,
            )
            CollectionDocument.objects.create(
                collection=collection,
                attachment=attachment,
            )

            # Create a markdown conversion for non-text files (same as conversation flow)
            if not attachment.content_type.startswith("text/"):
                md_key = f"{project.pk}/attachments/{attachment.file_name}.md"
                md_attachment = ChatConversationAttachment.objects.create(
                    project=project,
                    uploaded_by=attachment.uploaded_by,
                    key=md_key,
                    file_name=f"{attachment.file_name}.md",
                    content_type="text/markdown",
                    upload_state=AttachmentStatus.READY,
                    conversion_from=attachment.key,
                )
                default_storage.save(md_attachment.key, BytesIO(parsed_content.encode("utf8")))

        except Exception:
            logger.exception(
                "Failed to index project attachment %s into collection %s",
                attachment.pk,
                collection.pk,
            )

    return collection, backend
