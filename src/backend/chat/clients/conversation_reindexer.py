"""Standalone async generator for re-indexing a conversation's RAG collection."""

import asyncio
import logging
import uuid
from typing import AsyncGenerator

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string

from core.file_upload.enums import AttachmentStatus

from chat import models
from chat.vercel_ai_sdk.core import events_v4

logger = logging.getLogger(__name__)
document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)


async def reindex_conversation(
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
    claimed = await models.ChatConversation.objects.filter(
        pk=conversation.pk,
        collection_id__isnull=True,
    ).aupdate(collection_id="reindexing")
    if not claimed:
        return

    ready_attachments = [
        attachment
        async for attachment in models.ChatConversationAttachment.objects.filter(
            conversation=conversation,
            upload_state=AttachmentStatus.READY,
        )
    ]

    if not ready_attachments:
        return

    text_attachments_to_reindex = [
        a
        for a in ready_attachments
        if a.content_type.startswith("text/") and str(a.id) not in in_context_ids
    ]

    if not text_attachments_to_reindex:
        return

    _tool_call_id = str(uuid.uuid4())
    yield events_v4.ToolCallPart(
        tool_call_id=_tool_call_id,
        tool_name="conversation_resume",
        args={},
    )

    try:
        document_store = document_store_backend(collection_id=None)
        await document_store.acreate_collection(
            name=f"conversation-{conversation.pk}",
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Failed to create collection for conversation %s", conversation.pk)
        # Reset the sentinel so the next request can retry instead of staying stuck.
        conversation.collection_id = None
        await conversation.asave(update_fields=["collection_id", "updated_at"])
        yield events_v4.ToolResultPart(
            tool_call_id=_tool_call_id,
            result={"state": "error", "error": str(exc)},
        )
        return

    failed_documents = []
    for attachment in text_attachments_to_reindex:
        try:
            with default_storage.open(attachment.key, "rb") as file:
                content = file.read()
            await asyncio.to_thread(
                document_store.store_document,
                name=attachment.file_name.removesuffix(".md"),
                content=content.decode("utf-8"),
            )
        except Exception:  # pylint: disable=broad-except
            failed_documents.append(attachment.file_name)
            logger.exception(
                "Failed to re-index attachment %s for conversation %s",
                attachment.pk,
                conversation.pk,
            )

    conversation.collection_id = str(document_store.collection_id)
    await conversation.asave(update_fields=["collection_id", "updated_at"])

    result = (
        {"state": "partial", "failed_documents": failed_documents}
        if failed_documents
        else {"state": "done"}
    )
    yield events_v4.ToolResultPart(
        tool_call_id=_tool_call_id,
        result=result,
    )
