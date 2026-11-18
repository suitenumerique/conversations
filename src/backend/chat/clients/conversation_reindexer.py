"""Chat-turn side of a conversation re-index.

The turn claims the conversation, picks the attachments to store and hands them
to `reindex_conversation_task`, then waits on its result. The slow part runs on
a Celery worker (see `chat.agent_rag.conversation_reindexing`), so it is bounded
by the task time limits and completes even if the client disconnects.
"""

import asyncio
import uuid
from datetime import timedelta
from typing import AsyncGenerator

from django.db.models import Q
from django.utils import timezone

import structlog
from celery.exceptions import TimeoutError as CeleryTimeoutError

from core.file_upload.enums import AttachmentStatus

from chat import models
from chat.agent_rag.conversation_reindexing import CONCURRENT_REINDEX_RESULT, FAILED_RESULT
from chat.constants import (
    REINDEX_CLAIM_TTL_SECONDS,
    REINDEX_RESULT_TIMEOUT_SECONDS,
    TABULAR_MIME_TYPES,
    TEXT_MIME_PREFIX,
)
from chat.enums import CollectionIndexState
from chat.tasks import reindex_conversation_task
from chat.vercel_ai_sdk.core import events_v4

logger = structlog.get_logger(__name__)


def _busy_end() -> list[events_v4.Event]:
    """End the turn: the conversation is (still) being re-indexed.

    Always on a `document_parsing` call, never on `conversation_resume`: the UI
    opens its re-index error modal for any error there, whose copy says the
    assistant keeps going without the documents.
    """
    tool_call_id = str(uuid.uuid4())
    return [
        events_v4.ToolCallPart(tool_call_id=tool_call_id, tool_name="document_parsing", args={}),
        events_v4.ToolResultPart(tool_call_id=tool_call_id, result=dict(CONCURRENT_REINDEX_RESULT)),
        events_v4.FinishMessagePart(
            finish_reason=events_v4.FinishReason.ERROR,
            usage=events_v4.Usage(prompt_tokens=0, completion_tokens=0, co2_impact=0),
        ),
    ]


async def _claim(conversation: models.ChatConversation) -> bool:
    """Take the re-index claim: flip the row to INDEXING if nobody holds it.

    A claim older than the TTL belongs to a dead task and may be taken over.
    It is timed by `index_claimed_at`, not `updated_at`: an aborted turn's
    question gets folded into the conversation by the next turn, which moves
    `updated_at` forward and would keep a dead claim alive. A row with no claim
    time was claimed before the field existed and is taken over too.
    Known gap: a task started more than the TTL after its claim (worker
    backlog) is not dead, so it and the new claimer's task can both run.
    """
    now = timezone.now()
    stale_before = now - timedelta(seconds=REINDEX_CLAIM_TTL_SECONDS)
    return bool(
        await models.ChatConversation.objects.filter(
            Q(index_state__in=[CollectionIndexState.DEINDEXED, CollectionIndexState.ERROR])
            | Q(index_state=CollectionIndexState.INDEXING, index_claimed_at__lt=stale_before)
            | Q(index_state=CollectionIndexState.INDEXING, index_claimed_at__isnull=True),
            pk=conversation.pk,
        ).aupdate(index_state=CollectionIndexState.INDEXING, index_claimed_at=now, updated_at=now)
    )


async def _set_index_state(conversation, index_state):
    await models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(
        index_state=index_state, updated_at=timezone.now()
    )


async def _release_claim(conversation) -> None:
    """Set a row still INDEXING to ERROR, so the next turn retries at once."""
    await models.ChatConversation.objects.filter(
        pk=conversation.pk, index_state=CollectionIndexState.INDEXING
    ).aupdate(index_state=CollectionIndexState.ERROR, updated_at=timezone.now())


async def _has_failed(conversation, async_result) -> bool:
    """Whether the task is known to have ended in failure; False when unknown."""
    try:
        return bool(await asyncio.to_thread(async_result.failed))
    except Exception:  # pylint: disable=broad-except
        logger.warning("reindex_task_state_unknown", conversation_id=conversation.pk, exc_info=True)
        return False


async def _wait_for_rebuild(conversation, attachment_ids: list[str]) -> dict | None:
    """Run the rebuild task and return its tool result.

    None means the task may still be running (timeout, unknown state): the
    claim stays, and the caller ends the turn as busy.
    """
    # Publish, wait, revoke and forget are synchronous Redis round trips: run
    # them in threads to keep the event loop free for other streams.
    try:
        async_result = await asyncio.to_thread(
            reindex_conversation_task.delay, str(conversation.pk), attachment_ids
        )
    except Exception:  # pylint: disable=broad-except
        # No task exists: release the claim so the next turn retries.
        logger.exception("reindex_enqueue_failed", conversation_id=conversation.pk)
        await _release_claim(conversation)
        return dict(FAILED_RESULT)

    try:
        return await asyncio.to_thread(async_result.get, timeout=REINDEX_RESULT_TIMEOUT_SECONDS)
    except CeleryTimeoutError:
        # Still queued: revoke so it doesn't run after the turn moved on. A
        # running task is not stopped by revoke; the hard time limit caps it.
        await asyncio.to_thread(async_result.revoke)
        logger.warning("reindex_result_timeout", conversation_id=conversation.pk)
        return None
    except Exception:  # pylint: disable=broad-except
        # The task reports its own errors, so this is a crash, the hard time
        # limit, a lost worker, or the result backend failing. Only the last
        # leaves the task possibly running.
        if await _has_failed(conversation, async_result):
            logger.exception("reindex_task_failed", conversation_id=conversation.pk)
            await _release_claim(conversation)
            return dict(FAILED_RESULT)
        logger.exception("reindex_task_lost", conversation_id=conversation.pk)
        return None
    finally:
        await asyncio.to_thread(async_result.forget)


async def reindex_conversation(
    conversation: models.ChatConversation,
    in_context_ids: set[str],
) -> AsyncGenerator[events_v4.Event, None]:
    """
    Re-index READY attachments not already inlined in the context window.

    Only `tool_call_only` attachments (too large for context) need to be in the
    vector store; `full-context` attachments are already readable by the model.

    Emits a ToolCallPart/ToolResultPart pair so the UI shows progress, and an
    error finish when the conversation is (still) being re-indexed elsewhere.
    """
    if not await _claim(conversation):
        for event in _busy_end():
            yield event
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
        await _set_index_state(conversation, CollectionIndexState.UNINDEXED)
        return

    attachment_ids = [
        str(a.id)
        for a in ready_attachments
        if a.content_type.startswith(TEXT_MIME_PREFIX)
        and a.content_type not in TABULAR_MIME_TYPES
        and str(a.id) not in in_context_ids
        and not a.is_indexed
    ]
    if not attachment_ids:
        await _set_index_state(
            conversation,
            CollectionIndexState.INDEXED
            if conversation.collection_id
            else CollectionIndexState.UNINDEXED,
        )
        return

    tool_call_id = str(uuid.uuid4())
    yield events_v4.ToolCallPart(
        tool_call_id=tool_call_id, tool_name="conversation_resume", args={}
    )

    result = await _wait_for_rebuild(conversation, attachment_ids)
    if result is None or result.get("kind") == CONCURRENT_REINDEX_RESULT["kind"]:
        # Close the loader without an error, then end the turn as busy.
        yield events_v4.ToolResultPart(tool_call_id=tool_call_id, result={"state": "interrupted"})
        for event in _busy_end():
            yield event
        return
    yield events_v4.ToolResultPart(tool_call_id=tool_call_id, result=result)
