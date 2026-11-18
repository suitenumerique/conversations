"""Tests for reindex_conversation, the chat-turn side of a re-index.

The turn claims the row, picks the attachments, then waits on
`reindex_conversation_task`. The rebuild itself is covered in
`chat/tests/agent_rag/test_conversation_reindexing.py`.
"""

import asyncio
import logging
import threading
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

import pytest
from asgiref.sync import sync_to_async
from celery.exceptions import TimeoutError as CeleryTimeoutError

from core.file_upload.enums import AttachmentStatus

from chat import models
from chat.clients.conversation_reindexer import reindex_conversation
from chat.constants import REINDEX_CLAIM_TTL_SECONDS, REINDEX_RESULT_TIMEOUT_SECONDS
from chat.enums import CollectionIndexState
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.vercel_ai_sdk.core import events_v4

REINDEXER_LOGGER = "chat.clients.conversation_reindexer"
TASK_PATH = "chat.clients.conversation_reindexer.reindex_conversation_task"

# transaction=True is required so writes done via async threadpool connections
# (asave, aupdate) commit and are flushed via TRUNCATE between tests instead of
# leaking across them.
pytestmark = pytest.mark.django_db(transaction=True)


def _reindexer_records(caplog, event):
    """Reindexer records for `event` (structlog records carry a dict msg)."""
    return [r for r in caplog.records if r.name == REINDEXER_LOGGER and r.msg["event"] == event]


async def _deindexed_conversation(**kwargs):
    kwargs.setdefault("collection_id", None)
    kwargs.setdefault("index_state", CollectionIndexState.DEINDEXED)
    return await sync_to_async(ChatConversationFactory)(**kwargs)


async def _attachment(conversation, **kwargs):
    kwargs.setdefault("content_type", "text/markdown")
    return await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation, upload_state=AttachmentStatus.READY, **kwargs
    )


async def _collect(conversation, in_context_ids=frozenset()):
    return [event async for event in reindex_conversation(conversation, set(in_context_ids))]


def _task_returning(result=None, get_side_effect=None):
    """A patched task whose `.delay()` returns a fake AsyncResult."""
    async_result = MagicMock()
    async_result.get.return_value = result
    async_result.failed.return_value = False
    if get_side_effect is not None:
        async_result.get.side_effect = get_side_effect
    task = MagicMock()
    task.delay.return_value = async_result
    return task, async_result


def _assert_busy_end(events):
    """The busy result rides on a `document_parsing` call, then the turn ends.

    Never on `conversation_resume`: the UI opens its re-index error modal for
    any error there, whose copy says the assistant keeps going.
    """
    calls = {e.tool_call_id: e.tool_name for e in events if isinstance(e, events_v4.ToolCallPart)}
    busy = [
        e
        for e in events
        if isinstance(e, events_v4.ToolResultPart) and e.result.get("kind") == "concurrent_reindex"
    ]
    assert len(busy) == 1
    assert calls[busy[0].tool_call_id] == "document_parsing"
    assert isinstance(events[-1], events_v4.FinishMessagePart)
    assert events[-1].finish_reason == events_v4.FinishReason.ERROR


def _assert_resume_closed_without_error(events):
    resume_ids = [
        e.tool_call_id
        for e in events
        if isinstance(e, events_v4.ToolCallPart) and e.tool_name == "conversation_resume"
    ]
    assert len(resume_ids) == 1
    resume_result = next(
        e
        for e in events
        if isinstance(e, events_v4.ToolResultPart) and e.tool_call_id == resume_ids[0]
    )
    assert resume_result.result == {"state": "interrupted"}


@pytest.mark.asyncio
async def test_reindex_emits_events_and_saves_collection_id():
    """End to end (eager task): ToolCallPart + ToolResultPart, collection id saved."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    await _attachment(conversation)

    store = MagicMock()
    store.collection_id = "new-456"
    store.store_document.return_value = "doc-id"
    with (
        patch(
            "chat.agent_rag.conversation_reindexing.document_store_backend",
            MagicMock(return_value=store),
        ),
        patch(
            "chat.agent_rag.conversation_reindexing._read_attachment_bytes",
            return_value=b"data",
        ),
    ):
        events = await _collect(conversation)

    assert len(events) == 2
    assert isinstance(events[0], events_v4.ToolCallPart)
    assert events[0].tool_name == "conversation_resume"
    assert isinstance(events[1], events_v4.ToolResultPart)
    assert events[1].tool_call_id == events[0].tool_call_id
    assert events[1].result == {"state": "done"}
    assert store.store_document.call_count == 2

    await conversation.arefresh_from_db()
    assert conversation.collection_id == "new-456"
    assert conversation.index_state == CollectionIndexState.INDEXED


@pytest.mark.asyncio
async def test_reindex_enqueues_selected_ids_only():
    """Only out-of-context, unindexed, non-tabular text attachments are sent to the task."""
    conversation = await _deindexed_conversation()
    wanted = await _attachment(conversation, file_name="large.md")
    in_context = await _attachment(conversation, file_name="small.md")
    await _attachment(conversation, file_name="done.md", is_indexed=True)
    await _attachment(conversation, file_name="doc.pdf", content_type="application/pdf")
    await _attachment(conversation, file_name="data.csv", content_type="text/csv")

    task, async_result = _task_returning({"state": "done"})
    with patch(TASK_PATH, task):
        events = await _collect(conversation, {str(in_context.id)})

    task.delay.assert_called_once_with(str(conversation.pk), [str(wanted.id)])
    async_result.get.assert_called_once_with(timeout=REINDEX_RESULT_TIMEOUT_SECONDS)
    async_result.forget.assert_called_once()
    assert events[-1].result == {"state": "done"}


@pytest.mark.asyncio
async def test_reindex_passes_task_result_through():
    """The task's result dict is the tool result, and the turn goes on."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation, file_name="broken.md")
    result = {"state": "partial", "failed_documents": ["broken.md"]}

    task, _ = _task_returning(result)
    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    assert [type(e) for e in events] == [events_v4.ToolCallPart, events_v4.ToolResultPart]
    assert events[-1].result == result


@pytest.mark.asyncio
async def test_reindex_yields_nothing_when_no_ready_attachments():
    """No READY attachments: no events, no task, row back to UNINDEXED."""
    conversation = await _deindexed_conversation()
    task, _ = _task_returning()

    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    assert not events
    task.delay.assert_not_called()
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.UNINDEXED


@pytest.mark.asyncio
async def test_reindex_skips_in_context_attachments():
    """Nothing left to store: no events, no task, row back to UNINDEXED."""
    conversation = await _deindexed_conversation()
    att = await _attachment(conversation)
    task, _ = _task_returning()

    with patch(TASK_PATH, task):
        events = await _collect(conversation, {str(att.id)})

    assert not events
    task.delay.assert_not_called()
    await conversation.arefresh_from_db()
    assert conversation.collection_id is None
    assert conversation.index_state == CollectionIndexState.UNINDEXED


@pytest.mark.asyncio
async def test_reindex_all_indexed_sets_indexed():
    """Every attachment already indexed in an existing collection: INDEXED, no task."""
    conversation = await _deindexed_conversation(
        collection_id="col-1", index_state=CollectionIndexState.ERROR
    )
    await _attachment(conversation, is_indexed=True)
    task, _ = _task_returning()

    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    assert not events
    task.delay.assert_not_called()
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXED


@pytest.mark.asyncio
async def test_reindex_busy_when_indexing_in_progress():
    """A fresh INDEXING claim held elsewhere: busy events, no task, row untouched."""
    conversation = await _deindexed_conversation(
        index_state=CollectionIndexState.INDEXING, index_claimed_at=timezone.now()
    )
    await _attachment(conversation)
    task, _ = _task_returning()

    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    assert events[0].tool_name == "document_parsing"
    _assert_busy_end(events)
    task.delay.assert_not_called()
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXING


@pytest.mark.asyncio
async def test_reindex_reclaims_after_claim_ttl():
    """An INDEXING claim older than the TTL is taken over."""
    conversation = await _deindexed_conversation(
        index_state=CollectionIndexState.INDEXING,
        index_claimed_at=timezone.now() - timedelta(seconds=REINDEX_CLAIM_TTL_SECONDS + 1),
    )
    await _attachment(conversation)
    task, _ = _task_returning({"state": "done"})

    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    task.delay.assert_called_once()
    assert events[-1].result == {"state": "done"}


@pytest.mark.asyncio
async def test_reindex_claim_expiry_ignores_recent_updates():
    """A dead claim expires even when the conversation was saved since.

    An aborted turn leaves its question behind and the next turn folds it,
    which moves `updated_at` forward: the claim must not ride on it.
    """
    conversation = await _deindexed_conversation(
        index_state=CollectionIndexState.INDEXING,
        index_claimed_at=timezone.now() - timedelta(seconds=REINDEX_CLAIM_TTL_SECONDS + 1),
    )
    await _attachment(conversation)
    await models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(
        updated_at=timezone.now()
    )
    task, _ = _task_returning({"state": "done"})

    with patch(TASK_PATH, task):
        await _collect(conversation)

    task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_reindex_claims_indexing_row_without_claim_time():
    """An INDEXING row with no claim time (claimed before the field existed) is taken over."""
    conversation = await _deindexed_conversation(
        index_state=CollectionIndexState.INDEXING, index_claimed_at=None
    )
    await _attachment(conversation)
    task, _ = _task_returning({"state": "done"})

    with patch(TASK_PATH, task):
        await _collect(conversation)

    task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_reindex_claim_records_claim_time():
    """Taking the claim stamps `index_claimed_at`."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    before = timezone.now()
    task, _ = _task_returning({"state": "done"})

    with patch(TASK_PATH, task):
        await _collect(conversation)

    await conversation.arefresh_from_db()
    assert conversation.index_claimed_at >= before


@pytest.mark.asyncio
async def test_concurrent_reindex_enqueues_once():
    """Two turns racing on the same conversation: one task, one busy turn."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    task, _ = _task_returning({"state": "done"})
    barrier = asyncio.Barrier(2)

    async def attempt():
        await barrier.wait()  # both reach the claim step simultaneously
        return await _collect(conversation)

    with patch(TASK_PATH, task):
        results = await asyncio.gather(attempt(), attempt())

    task.delay.assert_called_once()
    assert sum(isinstance(r[-1], events_v4.FinishMessagePart) for r in results) == 1


@pytest.mark.asyncio
async def test_reindex_result_timeout_revokes_and_ends_turn():
    """The wait times out: revoke, forget, end the turn as busy; the claim stays."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    task, async_result = _task_returning(get_side_effect=CeleryTimeoutError())

    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    async_result.revoke.assert_called_once()
    async_result.forget.assert_called_once()
    _assert_resume_closed_without_error(events)
    _assert_busy_end(events)
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXING


@pytest.mark.asyncio
async def test_reindex_task_lost_claim_ends_turn_as_busy():
    """The task found the row no longer INDEXING: same busy end, not the re-index modal."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    task, _ = _task_returning({"state": "error", "kind": "concurrent_reindex", "error": "busy"})

    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    _assert_resume_closed_without_error(events)
    _assert_busy_end(events)


@pytest.mark.asyncio
async def test_reindex_task_lost_ends_turn(caplog):
    """The task died or the result backend failed: no revoke, end the turn as busy."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    task, async_result = _task_returning(get_side_effect=RuntimeError("worker lost"))

    caplog.set_level(logging.ERROR, logger=REINDEXER_LOGGER)
    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    async_result.revoke.assert_not_called()
    async_result.forget.assert_called_once()
    _assert_resume_closed_without_error(events)
    _assert_busy_end(events)
    assert len(_reindexer_records(caplog, "reindex_task_lost")) == 1
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXING


@pytest.mark.asyncio
async def test_reindex_task_failed_releases_claim_and_continues(caplog):
    """The task definitely failed (error, hard time limit, worker lost): release to ERROR.

    The turn goes on without the documents, so the next turn retries at once
    instead of waiting for the claim to expire.
    """
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    task, async_result = _task_returning(get_side_effect=RuntimeError("TimeLimitExceeded"))
    async_result.failed.return_value = True

    caplog.set_level(logging.ERROR, logger=REINDEXER_LOGGER)
    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    assert [type(e) for e in events] == [events_v4.ToolCallPart, events_v4.ToolResultPart]
    assert events[0].tool_name == "conversation_resume"
    assert events[-1].result["state"] == "error"
    assert events[-1].result["kind"] == "rag_error"
    assert len(_reindexer_records(caplog, "reindex_task_failed")) == 1
    async_result.forget.assert_called_once()
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR


@pytest.mark.asyncio
async def test_reindex_task_failed_keeps_a_claim_taken_over():
    """Releasing to ERROR only touches a row still INDEXING."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)

    def fail_after_reindexed(timeout):
        assert timeout == REINDEX_RESULT_TIMEOUT_SECONDS
        models.ChatConversation.objects.filter(pk=conversation.pk).update(
            index_state=CollectionIndexState.INDEXED
        )
        raise RuntimeError("worker lost")

    task, async_result = _task_returning(get_side_effect=fail_after_reindexed)
    async_result.failed.return_value = True

    with patch(TASK_PATH, task):
        await _collect(conversation)

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXED


@pytest.mark.asyncio
async def test_reindex_unknown_task_state_ends_turn_as_busy():
    """`.failed()` itself fails (result backend down): the task may be running, stay busy."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    task, async_result = _task_returning(get_side_effect=ConnectionError("redis down"))
    async_result.failed.side_effect = ConnectionError("redis down")

    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    _assert_busy_end(events)
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXING


@pytest.mark.asyncio
async def test_reindex_enqueue_failure_sets_error_and_continues(caplog):
    """The broker is down: release the claim to ERROR, report rag_error, turn goes on."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    task = MagicMock()
    task.delay.side_effect = ConnectionError("broker down")

    caplog.set_level(logging.ERROR, logger=REINDEXER_LOGGER)
    with patch(TASK_PATH, task):
        events = await _collect(conversation)

    assert [type(e) for e in events] == [events_v4.ToolCallPart, events_v4.ToolResultPart]
    assert events[-1].result["state"] == "error"
    assert events[-1].result["kind"] == "rag_error"
    assert len(_reindexer_records(caplog, "reindex_enqueue_failed")) == 1
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR


@pytest.mark.asyncio
async def test_reindex_cancelled_wait_does_not_revoke():
    """A turn cancelled mid-wait (client gone) leaves the task running."""
    conversation = await _deindexed_conversation()
    await _attachment(conversation)
    waiting = threading.Event()
    release = threading.Event()

    def blocking_get(timeout):
        assert timeout == REINDEX_RESULT_TIMEOUT_SECONDS
        waiting.set()
        release.wait(5)
        return {"state": "done"}

    task, async_result = _task_returning(get_side_effect=blocking_get)
    with patch(TASK_PATH, task):
        consumer = asyncio.create_task(_collect(conversation))
        await asyncio.to_thread(waiting.wait, 5)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer
        release.set()

    async_result.revoke.assert_not_called()
