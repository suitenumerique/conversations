"""Centralized collection lookup, creation, and re-indexing for conversations."""

import logging
from typing import Type

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string

from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend
from chat.agent_rag.document_rag_backends.registry import get_backend_key
from chat.models import ChatConversationAttachment, Collection, CollectionDocument

logger = logging.getLogger(__name__)


def _current_backend_key() -> str:
    return get_backend_key(settings.RAG_DOCUMENT_SEARCH_BACKEND)


def _default_backend_class() -> Type[BaseRagBackend]:
    return import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)


# ------------------------------------------------------------------ #
# Sync helpers
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


def index_missing_attachments(conversation, user_sub: str, backend_class=None):
    """Ensure all conversation attachments are indexed in the current backend.

    Finds original attachments (not markdown conversions) that don't yet have a
    CollectionDocument in the current backend's collection, and indexes them.
    Creates the collection if needed.

    Returns (Collection, BaseRagBackend), or (None, None) when the conversation
    has no indexable attachments.
    """

    indexable = ChatConversationAttachment.objects.filter(
        conversation=conversation,
        conversion_from__isnull=True,
    )
    if not indexable.exists():
        collection = get_conversation_collection(conversation)
        if collection:
            backend_cls = backend_class or _default_backend_class()
            return collection, backend_cls(collection.external_id)
        return None, None

    collection, backend = get_or_create_conversation_collection(
        conversation,
        backend_class=backend_class,
    )

    indexed_ids = set(
        CollectionDocument.objects.filter(
            collection=collection,
        ).values_list("attachment_id", flat=True)
    )
    missing = indexable.exclude(pk__in=indexed_ids)

    for attachment in missing:
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
                "Failed to index attachment %s into collection %s",
                attachment.pk,
                collection.pk,
            )

    return collection, backend


# ------------------------------------------------------------------ #
# Async helpers
# ------------------------------------------------------------------ #


async def aget_conversation_collection(conversation):
    """Async variant of get_conversation_collection. TODO: remove if unused"""

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
