"""Snapshot the La Suite Docs documents linked in a user message."""

import asyncio
import uuid
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import DatabaseError
from django.utils.module_loading import import_string

import structlog
from botocore.exceptions import BotoCoreError, ClientError

from core.file_upload.mixins import AttachmentMixin
from core.log_fields import safe_error_fields

from chat import models
from chat.constants import MARKDOWN_MIME_TYPE
from chat.docs_client import (
    DocsClient,
    DocsDocument,
    DocsFetchError,
    DocsFetchFailure,
    docs_document_url,
    safe_file_stem,
)

# Keep at the top of the file to avoid mocking issues
document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

logger = structlog.get_logger(__name__)

# What the model is told when a pasted Docs link could not be read.
DOCS_FETCH_FAILURE_REASONS = {
    DocsFetchFailure.UNAUTHENTICATED: (
        "the user's Docs session has expired or they have never signed into Docs; "
        "they should sign into Docs, then try again"
    ),
    DocsFetchFailure.FORBIDDEN: "the user does not have access to this document",
    DocsFetchFailure.NOT_FOUND: "the document does not exist or has been deleted",
    DocsFetchFailure.UNAVAILABLE: "Docs is currently unavailable; the user can try again later",
    DocsFetchFailure.TOO_LARGE: "the document is too large to be read",
    DocsFetchFailure.EMPTY: "the document is empty",
    DocsFetchFailure.STORAGE_FAILED: (
        "the document could not be saved to the conversation; the user can try again later"
    ),
    DocsFetchFailure.OVER_LIMIT: (
        "too many Docs links were pasted in one message; "
        "the user can paste this link again in another message"
    ),
}


def docs_read_note(document_id: uuid.UUID, file_name: str) -> str:
    """Tell the model that a pasted Docs link was read and attached as ``file_name``."""
    return (
        "[Internal context] The Docs document linked at "
        f"{docs_document_url(document_id)} has been read and attached to this "
        f'conversation as "{file_name}". Use that document to answer; '
        "do not say you cannot open the link."
    )


def limit_docs_links(document_ids: list[uuid.UUID]) -> tuple[list[uuid.UUID], list[str]]:
    """Keep the first ``DOCS_LINKS_MAX_PER_MESSAGE`` links to read.

    Returns:
        The ids to read, and a note for each ignored link so the model can tell the user.
    """
    limit = settings.DOCS_LINKS_MAX_PER_MESSAGE
    ignored = document_ids[limit:]
    if ignored:
        logger.info("docs_links_over_limit", ignored=len(ignored), limit=limit)
    return document_ids[:limit], [
        docs_failure_note(document_id, DocsFetchFailure.OVER_LIMIT) for document_id in ignored
    ]


def docs_failure_note(document_id: uuid.UUID, failure: DocsFetchFailure) -> str:
    """Tell the model why a pasted Docs link could not be read."""
    return (
        "[Internal context] The Docs document linked at "
        f"{docs_document_url(document_id)} could not be read: "
        f"{DOCS_FETCH_FAILURE_REASONS[failure]}. Explain this to the user."
    )


async def _delete_snapshot(
    conversation: models.ChatConversation, attachment: models.ChatConversationAttachment
) -> None:
    """Delete a Docs snapshot: its row, then its RAG document and S3 object.

    The row goes first, so a failure never leaves a listed snapshot whose content
    is gone. RAG and S3 cleanups are best-effort, like the attachment delete
    endpoint: a failure leaves orphaned storage.

    Raises:
        DatabaseError: the row could not be deleted; nothing else was touched.
    """
    await attachment.adelete()
    if attachment.rag_document_id and conversation.collection_id:
        try:
            await document_store_backend(conversation.collection_id).adelete_document(
                attachment.rag_document_id
            )
        except Exception as exc:  # pylint: disable=broad-except #noqa: BLE001
            logger.error(
                "docs_snapshot_rag_delete_failed",
                attachment_id=attachment.pk,
                rag_document_id=attachment.rag_document_id,
                **safe_error_fields(exc),
            )
    try:
        await asyncio.to_thread(default_storage.delete, attachment.key)
    except BotoCoreError, ClientError, OSError:
        logger.exception("docs_snapshot_file_delete_failed", attachment_id=attachment.pk)


async def _store_snapshot(
    conversation: models.ChatConversation,
    user,
    document_id: uuid.UUID,
    document: DocsDocument,
    content: bytes,
) -> models.ChatConversationAttachment:
    """Store a new snapshot of a Docs document; the previous ones are left in place.

    A stored file whose row cannot be created is deleted, so it is never orphaned.
    """
    key = f"{conversation.pk}/{AttachmentMixin.ATTACHMENTS_FOLDER}/{uuid.uuid4()}.md"
    await asyncio.to_thread(default_storage.save, key, BytesIO(content))
    try:
        return await models.ChatConversationAttachment.objects.acreate(
            conversation=conversation,
            uploaded_by=user,
            key=key,
            file_name=f"{safe_file_stem(document.title)}.md",
            content_type=MARKDOWN_MIME_TYPE,
            size=len(content),
            upload_state=models.AttachmentStatus.READY,
            docs_document_id=document_id,
        )
    except DatabaseError:
        await asyncio.to_thread(default_storage.delete, key)
        raise


async def store_docs_snapshots(
    conversation: models.ChatConversation, user, session, document_ids: list[uuid.UUID]
) -> tuple[list[models.ChatConversationAttachment], list[str]]:
    """Snapshot the linked Docs documents into conversation attachments.

    Each link gets a note for the model: a successful read names the attached
    document, so the model ties it to the pasted URL; a failed read never
    aborts the turn and explains why the document is missing.

    The previous snapshots of these documents are kept: once the new ones are
    indexed, `delete_replaced_snapshots` deletes them; if indexing fails,
    `discard_snapshots` deletes the new ones instead.

    Returns:
        The stored snapshots to index, and the notes for every link.
    """
    docs_client = DocsClient()
    # Fetch in parallel so slow links cost one Docs timeout, not one each.
    fetched = await asyncio.gather(
        *(
            docs_client.fetch_document_markdown(document_id, session)
            for document_id in document_ids
        ),
        return_exceptions=True,
    )
    snapshots = []
    notes = []
    for document_id, document in zip(document_ids, fetched, strict=True):
        try:
            if isinstance(document, BaseException):
                raise document
            if not document.content.strip():
                raise DocsFetchError(DocsFetchFailure.EMPTY)
            content = document.content.encode("utf-8")
            if len(content) > settings.ATTACHMENT_MAX_SIZE:
                raise DocsFetchError(DocsFetchFailure.TOO_LARGE)
            snapshot = await _store_snapshot(conversation, user, document_id, document, content)
        except PermissionDenied:
            failure = DocsFetchFailure.UNAUTHENTICATED
        except DocsFetchError as exc:
            failure = exc.reason
        except BotoCoreError, ClientError, OSError, DatabaseError:
            logger.exception("docs_snapshot_store_failed", document_id=document_id)
            failure = DocsFetchFailure.STORAGE_FAILED
        except Exception as exc:  # pylint: disable=broad-except #noqa: BLE001
            # No traceback: the error text can quote the document.
            logger.error("docs_snapshot_failed", document_id=document_id, **safe_error_fields(exc))
            failure = DocsFetchFailure.UNAVAILABLE
        else:
            snapshots.append(snapshot)
            notes.append(docs_read_note(document_id, snapshot.file_name))
            continue
        notes.append(docs_failure_note(document_id, failure))
    return snapshots, notes


async def delete_replaced_snapshots(
    conversation: models.ChatConversation, snapshots: list[models.ChatConversationAttachment]
) -> None:
    """Delete the previous snapshots of the documents ``snapshots`` were just taken of.

    A previous snapshot that cannot be deleted is left for the next paste to delete.
    """
    for snapshot in snapshots:
        try:
            async for previous in models.ChatConversationAttachment.objects.filter(
                conversation=conversation, docs_document_id=snapshot.docs_document_id
            ).exclude(pk=snapshot.pk):
                await _delete_snapshot(conversation, previous)
        except DatabaseError:
            logger.exception("docs_snapshot_replace_failed", document_id=snapshot.docs_document_id)


async def discard_snapshots(
    conversation: models.ChatConversation, snapshots: list[models.ChatConversationAttachment]
) -> None:
    """Delete snapshots that could not be indexed, so the previous ones stay in use."""
    # Reloaded: indexing may have stored a RAG document id before it failed.
    async for snapshot in models.ChatConversationAttachment.objects.filter(
        pk__in=[snapshot.pk for snapshot in snapshots]
    ):
        try:
            await _delete_snapshot(conversation, snapshot)
        except DatabaseError:
            logger.exception("docs_snapshot_discard_failed", attachment_id=snapshot.pk)
