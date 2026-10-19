"""Snapshot the La Suite Docs documents linked in a user message."""

import asyncio
import logging
import uuid
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string

from botocore.exceptions import BotoCoreError, ClientError

from core.file_upload.mixins import AttachmentMixin

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

logger = logging.getLogger(__name__)

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
}


def docs_read_note(document_id: uuid.UUID, file_name: str) -> str:
    """Tell the model that a pasted Docs link was read and attached as ``file_name``."""
    return (
        "[Internal context] The Docs document linked at "
        f"{docs_document_url(document_id)} has been read and attached to this "
        f'conversation as "{file_name}". Use that document to answer; '
        "do not say you cannot open the link."
    )


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
    """Delete a Docs snapshot: its RAG document, its S3 object, then its row.

    RAG and S3 cleanups are best-effort, like the attachment delete endpoint:
    a failure leaves orphaned storage but never keeps the stale snapshot.
    """
    if attachment.rag_document_id and conversation.collection_id:
        try:
            await document_store_backend(conversation.collection_id).adelete_document(
                attachment.rag_document_id
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Failed to delete RAG document %s of a Docs snapshot",
                attachment.rag_document_id,
            )
    try:
        await asyncio.to_thread(default_storage.delete, attachment.key)
    except BotoCoreError, ClientError, OSError:
        logger.exception("Failed to delete S3 object %s of a Docs snapshot", attachment.key)
    await attachment.adelete()


async def _store_snapshot(
    conversation: models.ChatConversation,
    user,
    document_id: uuid.UUID,
    document: DocsDocument,
    content: bytes,
) -> models.ChatConversationAttachment:
    """Replace the conversation's snapshot of a Docs document with a new one.

    The new snapshot is stored before the previous ones are deleted, so a storage
    failure never loses the previous snapshot.
    """
    key = f"{conversation.pk}/{AttachmentMixin.ATTACHMENTS_FOLDER}/{uuid.uuid4()}.md"
    await asyncio.to_thread(default_storage.save, key, BytesIO(content))
    snapshot = await models.ChatConversationAttachment.objects.acreate(
        conversation=conversation,
        uploaded_by=user,
        key=key,
        file_name=f"{safe_file_stem(document.title)}.md",
        content_type=MARKDOWN_MIME_TYPE,
        size=len(content),
        upload_state=models.AttachmentStatus.READY,
        docs_document_id=document_id,
        docs_updated_at=document.updated_at,
    )
    async for previous in models.ChatConversationAttachment.objects.filter(
        conversation=conversation, docs_document_id=document_id
    ).exclude(pk=snapshot.pk):
        await _delete_snapshot(conversation, previous)
    return snapshot


async def store_docs_snapshots(
    conversation: models.ChatConversation, user, session, document_ids: list[uuid.UUID]
) -> tuple[list[models.ChatConversationAttachment], list[str]]:
    """Snapshot the linked Docs documents into conversation attachments.

    Each link gets a note for the model: a successful read names the attached
    document, so the model ties it to the pasted URL; a failed read never
    aborts the turn and explains why the document is missing.

    Returns:
        The stored snapshots to index, and the notes for every link.
    """
    docs_client = DocsClient()
    snapshots = []
    notes = []
    for document_id in document_ids:
        try:
            document = await docs_client.fetch_document_markdown(document_id, session)
            content = document.content.encode("utf-8")
            if len(content) > settings.ATTACHMENT_MAX_SIZE:
                raise DocsFetchError(DocsFetchFailure.TOO_LARGE)
        except PermissionDenied:
            failure = DocsFetchFailure.UNAUTHENTICATED
        except DocsFetchError as exc:
            failure = exc.reason
        else:
            snapshot = await _store_snapshot(conversation, user, document_id, document, content)
            snapshots.append(snapshot)
            notes.append(docs_read_note(document_id, snapshot.file_name))
            continue
        notes.append(docs_failure_note(document_id, failure))
    return snapshots, notes
