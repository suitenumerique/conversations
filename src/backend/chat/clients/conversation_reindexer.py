"""Standalone async generator for re-indexing a conversation's RAG collection."""

import asyncio
import logging
import uuid
from datetime import timedelta
from typing import AsyncGenerator

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone
from django.utils.module_loading import import_string

from core.file_upload.enums import AttachmentStatus

from chat import models
from chat.clients.error_classification import RAG_ERROR, resolve_rag_error_code
from chat.constants import TEXT_MIME_PREFIX
from chat.enums import CollectionIndexState
from chat.vercel_ai_sdk.core import events_v4

logger = logging.getLogger(__name__)
document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)


async def _read_attachment_bytes(key: str) -> bytes:
    def _read():
        with default_storage.open(key, "rb") as f:
            return f.read()

    return await asyncio.to_thread(_read)


async def reindex_conversation(  # pylint: disable=too-many-locals
    conversation: models.ChatConversation,
    in_context_ids: set[str],
) -> AsyncGenerator[events_v4.Event, None]:
    """
    Re-index READY attachments not already inlined in the context window.

    Only `tool_call_only` attachments (too large for context) need to be in the
    vector store; `full-context` attachments are already readable by the model.

    Emits a ToolCallPart/ToolResultPart pair so the UI shows progress.
    On collection creation failure: logs and returns without RAG (conversation continues).
    On individual attachment failure: logs and continues with remaining attachments.
    """
    # The timeout lets a second request reclaim a stuck INDEXING row. Default is generous
    # (10 min) because reindex iterates over attachments: one storage read + one HTTP call each.
    timeout = timedelta(seconds=settings.REINDEX_CLAIM_TIMEOUT_SECONDS)
    claimed = await models.ChatConversation.objects.filter(
        Q(
            pk=conversation.pk,
            index_state__in=[
                CollectionIndexState.DEINDEXED,
                CollectionIndexState.ERROR,
            ],
        )
        | Q(
            pk=conversation.pk,
            index_state=CollectionIndexState.INDEXING,
            updated_at__lt=timezone.now() - timeout,
        )
    ).aupdate(index_state=CollectionIndexState.INDEXING, updated_at=timezone.now())
    if not claimed:
        _tool_call_id = str(uuid.uuid4())
        yield events_v4.ToolCallPart(
            tool_call_id=_tool_call_id,
            tool_name="document_parsing",
            args={},
        )
        yield events_v4.ToolResultPart(
            tool_call_id=_tool_call_id,
            result={
                "state": "error",
                "kind": "concurrent_reindex",
                "error": "Documents are currently being re-indexed. Please retry in a moment.",
            },
        )
        yield events_v4.FinishMessagePart(
            finish_reason=events_v4.FinishReason.ERROR,
            usage=events_v4.Usage(prompt_tokens=0, completion_tokens=0, co2_impact=0),
        )
        return
    # Refresh: the in-memory object may have a stale collection_id (e.g. when reclaiming
    # a timed-out INDEXING row whose collection was already created by the previous attempt).
    await conversation.arefresh_from_db(fields=["collection_id", "index_state"])

    ready_attachments = [
        attachment
        async for attachment in models.ChatConversationAttachment.objects.filter(
            conversation=conversation,
            upload_state=AttachmentStatus.READY,
        )
    ]

    if not ready_attachments:
        await models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(
            index_state=CollectionIndexState.UNINDEXED,
            updated_at=timezone.now(),
        )
        return

    text_attachments_to_reindex = [
        a
        for a in ready_attachments
        if a.content_type.startswith(TEXT_MIME_PREFIX)
        and str(a.id) not in in_context_ids
        and not a.is_indexed
    ]

    if not text_attachments_to_reindex:
        new_state = (
            CollectionIndexState.INDEXED
            if conversation.collection_id
            else CollectionIndexState.UNINDEXED
        )
        await models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(
            index_state=new_state,
            updated_at=timezone.now(),
        )
        return

    _tool_call_id = str(uuid.uuid4())
    yield events_v4.ToolCallPart(
        tool_call_id=_tool_call_id,
        tool_name="conversation_resume",
        args={},
    )

    # Reuse existing collection if available so partial-failure retries add only
    # the missing documents rather than rebuilding from scratch.
    existing_collection_id = conversation.collection_id
    document_store = document_store_backend(collection_id=existing_collection_id)
    if not existing_collection_id:
        try:
            await document_store.acreate_collection(
                name=f"conversation-{conversation.pk}",
            )
        except Exception as exc:  # pylint: disable=broad-except
            error_kind = resolve_rag_error_code(exc)
            logger.exception(
                "Failed to create collection for conversation %s (%s)",
                conversation.pk,
                error_kind,
            )
            await models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(
                index_state=CollectionIndexState.ERROR,
                collection_id=None,
                updated_at=timezone.now(),
            )
            await models.ChatConversationAttachment.objects.filter(
                conversation=conversation,
            ).aupdate(is_indexed=False, rag_document_id=None)
            yield events_v4.ToolResultPart(
                tool_call_id=_tool_call_id,
                result={
                    "state": "error",
                    "kind": error_kind,
                    "error": str(exc),
                },
            )
            return

    failed_documents = []
    last_failure_kind: str | None = None
    for attachment in text_attachments_to_reindex:
        try:
            content = await _read_attachment_bytes(attachment.key)
            rag_document_id = await asyncio.to_thread(
                document_store.store_document,
                name=attachment.file_name.removesuffix(".md"),
                content=content.decode("utf-8"),
            )
            await models.ChatConversationAttachment.objects.filter(pk=attachment.pk).aupdate(
                is_indexed=True,
                rag_document_id=rag_document_id or None,
            )
        except Exception as exc:  # pylint: disable=broad-except
            failed_documents.append(attachment.file_name)
            last_failure_kind = resolve_rag_error_code(exc)
            logger.exception(
                "Failed to re-index attachment %s for conversation %s (%s)",
                attachment.pk,
                conversation.pk,
                last_failure_kind,
            )

    any_failed = bool(failed_documents)
    all_failed = len(failed_documents) == len(text_attachments_to_reindex)

    update_fields = {
        "index_state": CollectionIndexState.ERROR if any_failed else CollectionIndexState.INDEXED,
        "updated_at": timezone.now(),
    }

    update_fields["collection_id"] = str(document_store.collection_id)
    if all_failed:
        result = {
            "state": "error",
            "kind": last_failure_kind or RAG_ERROR,
            "error": "Documents could not be re-indexed.",
        }
    else:
        # No aggregate kind on partial failures: different documents may have
        # failed for different reasons; the modal shows the per-document list.
        result = (
            {"state": "partial", "failed_documents": failed_documents}
            if failed_documents
            else {"state": "done"}
        )

    await models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(**update_fields)
    yield events_v4.ToolResultPart(
        tool_call_id=_tool_call_id,
        result=result,
    )
