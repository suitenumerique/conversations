"""Rebuild a re-indexed conversation's RAG collection.

Runs in `reindex_conversation_task`, enqueued by the chat turn
(`chat.clients.conversation_reindexer.reindex_conversation`) which waits on the
result. The turn has already taken the re-index claim and picked the
attachments; this does the slow part off the web process: create or reuse the
collection, store each attachment, and write the final index state. Because it
runs on a worker, it completes even if the client disconnects mid-turn.

The returned dict is the `conversation_resume` tool result the UI renders.
"""

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.module_loading import import_string

import structlog
from celery.exceptions import SoftTimeLimitExceeded

from core.file_upload.enums import AttachmentStatus

from chat import models
from chat.clients.error_classification import RAG_ERROR, resolve_rag_error_code
from chat.enums import CollectionIndexState

logger = structlog.get_logger(__name__)
document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

CONCURRENT_REINDEX_RESULT = {
    "state": "error",
    "kind": "concurrent_reindex",
    "error": "Documents are currently being re-indexed. Please retry in a moment.",
}
FAILED_RESULT = {
    "state": "error",
    "kind": RAG_ERROR,
    "error": "Documents could not be re-indexed.",
}


def _read_attachment_bytes(key: str) -> bytes:
    with default_storage.open(key, "rb") as f:
        return f.read()


def _set_index_state(conversation_id, **fields):
    models.ChatConversation.objects.filter(pk=conversation_id).update(
        updated_at=timezone.now(), **fields
    )


def rebuild_conversation_collection(conversation_id: str, attachment_ids: list[str]) -> dict:
    """Store `attachment_ids` in the conversation's collection; return the tool result."""
    try:
        conversation = models.ChatConversation.objects.get(pk=conversation_id)
    except models.ChatConversation.DoesNotExist:
        logger.info("reindex_conversation_gone", conversation_id=conversation_id)
        return dict(FAILED_RESULT)

    # The turn claimed the row before enqueueing. A row no longer INDEXING was
    # de-indexed again or its stale claim was taken over: leave it alone.
    if conversation.index_state != CollectionIndexState.INDEXING:
        logger.info(
            "reindex_claim_lost",
            conversation_id=conversation_id,
            index_state=conversation.index_state,
        )
        return dict(CONCURRENT_REINDEX_RESULT)

    # Deleted, no longer READY or already stored since the turn picked them: skip.
    attachments = list(
        models.ChatConversationAttachment.objects.filter(
            pk__in=attachment_ids,
            conversation_id=conversation_id,
            upload_state=AttachmentStatus.READY,
            is_indexed=False,
        )
    )

    # Reuse an existing collection so partial-failure retries add only the
    # missing documents rather than rebuilding from scratch.
    document_store = document_store_backend(collection_id=conversation.collection_id)
    if not conversation.collection_id:
        try:
            document_store.create_collection(name=f"conversation-{conversation.pk}")
        except Exception as exc:  # pylint: disable=broad-except
            error_kind = resolve_rag_error_code(exc)
            logger.exception(
                "reindex_collection_create_failed",
                conversation_id=conversation_id,
                error_kind=error_kind,
            )
            _set_index_state(
                conversation_id, index_state=CollectionIndexState.ERROR, collection_id=None
            )
            models.ChatConversationAttachment.objects.filter(
                conversation_id=conversation_id,
            ).update(is_indexed=False, rag_document_id=None)
            return {"state": "error", "kind": error_kind, "error": str(exc)}
        # Record it now: if the worker dies mid-loop, the stored attachments
        # (is_indexed=True) must still point at a collection the row knows.
        models.ChatConversation.objects.filter(pk=conversation_id).update(
            collection_id=str(document_store.collection_id)
        )

    try:
        failed_documents, last_failure_kind = _store_attachments(
            document_store, attachments, conversation_id
        )
    except SoftTimeLimitExceeded:
        # Keep what was stored: the next turn re-claims from ERROR and adds
        # only the attachments still not indexed.
        logger.error("reindex_time_limit_exceeded", conversation_id=conversation_id)
        _set_index_state(
            conversation_id,
            index_state=CollectionIndexState.ERROR,
            collection_id=str(document_store.collection_id),
        )
        return dict(FAILED_RESULT)

    _set_index_state(
        conversation_id,
        index_state=(
            CollectionIndexState.ERROR if failed_documents else CollectionIndexState.INDEXED
        ),
        collection_id=str(document_store.collection_id),
    )
    return _tool_result(failed_documents, len(attachments), last_failure_kind)


def _store_attachments(document_store, attachments, conversation_id):
    """Store each attachment; return the failed file names and the last failure kind.

    One failed document does not stop the others. The soft time limit does.
    """
    failed_documents = []
    last_failure_kind: str | None = None
    for attachment in attachments:
        try:
            content = _read_attachment_bytes(attachment.key)
            rag_document_id = document_store.store_document(
                name=attachment.file_name.removesuffix(".md"),
                content=content.decode("utf-8"),
            )
            models.ChatConversationAttachment.objects.filter(pk=attachment.pk).update(
                is_indexed=True,
                rag_document_id=rag_document_id or None,
            )
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            failed_documents.append(attachment.file_name)
            last_failure_kind = resolve_rag_error_code(exc)
            logger.exception(
                "reindex_attachment_failed",
                attachment_id=attachment.pk,
                conversation_id=conversation_id,
                error_kind=last_failure_kind,
            )
    return failed_documents, last_failure_kind


def _tool_result(failed_documents, total, last_failure_kind):
    if failed_documents and len(failed_documents) == total:
        return {**FAILED_RESULT, "kind": last_failure_kind or RAG_ERROR}
    # No aggregate kind on partial failures: different documents may have
    # failed for different reasons; the modal shows the per-document list.
    if failed_documents:
        return {"state": "partial", "failed_documents": failed_documents}
    return {"state": "done"}
