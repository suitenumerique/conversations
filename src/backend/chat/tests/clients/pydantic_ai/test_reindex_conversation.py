"""Tests for reindex_conversation."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import requests
from asgiref.sync import sync_to_async

from core.file_upload.enums import AttachmentStatus

from chat import models
from chat.clients.conversation_reindexer import reindex_conversation
from chat.enums import CollectionIndexState
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.vercel_ai_sdk.core import events_v4

REINDEXER_LOGGER = "chat.clients.conversation_reindexer"

# transaction=True is required so writes done via async threadpool connections
# (asave, aupdate) commit and are flushed via TRUNCATE between tests instead of
# leaking across them.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
async def test_reindex_emits_events_and_saves_collection_id():
    """Re-indexing emits ToolCallPart + ToolResultPart and saves collection_id."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
    )

    mock_store = MagicMock()
    mock_store.collection_id = "new-456"
    mock_store.acreate_collection = AsyncMock()

    mock_backend = MagicMock(return_value=mock_store)

    to_thread_calls = []

    async def capture_to_thread(func, *args, **kwargs):
        to_thread_calls.append(func)

    with (
        patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", side_effect=capture_to_thread),
    ):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)

    assert len(events) == 2
    assert isinstance(events[0], events_v4.ToolCallPart)
    assert events[0].tool_name == "conversation_resume"
    assert isinstance(events[1], events_v4.ToolResultPart)
    assert events[1].result == {"state": "done"}

    # store_document (not parse_and_store_document) should be called for text/* attachments
    assert len(to_thread_calls) == 2
    assert all(func == mock_store.store_document for func in to_thread_calls)

    await conversation.arefresh_from_db()
    assert conversation.collection_id == "new-456"


@pytest.mark.asyncio
async def test_reindex_yields_nothing_when_no_ready_attachments():
    """No events yielded and collection_id stays None when no READY attachments."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.PENDING,
    )

    events = []
    async for event in reindex_conversation(conversation, in_context_ids=set()):
        events.append(event)

    assert not events
    await conversation.arefresh_from_db()
    assert conversation.collection_id is None


@pytest.mark.asyncio
async def test_reindex_yields_error_event_on_collection_creation_failure(caplog):
    """Error event yielded when acreate_collection raises; attachment metadata fully rolled back."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    attachment = await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        is_indexed=False,
        rag_document_id="stale-rag-id",
    )

    mock_store = MagicMock()
    mock_store.collection_id = None
    mock_store.acreate_collection = AsyncMock(side_effect=RuntimeError("Albert down"))
    mock_backend = MagicMock(return_value=mock_store)

    caplog.set_level(logging.ERROR, logger=REINDEXER_LOGGER)
    with patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)

    assert len(events) == 2
    assert isinstance(events[0], events_v4.ToolCallPart)
    assert events[0].tool_name == "conversation_resume"
    assert isinstance(events[1], events_v4.ToolResultPart)
    assert events[1].result["state"] == "error"
    assert events[1].result["kind"] == "rag_error"

    create_failures = [r for r in caplog.records if "Failed to create collection" in r.getMessage()]
    assert len(create_failures) == 1
    assert create_failures[0].levelno == logging.ERROR
    # logger.exception attaches exc_info — a plain logger.error would not.
    assert create_failures[0].exc_info is not None
    assert "rag_error" in create_failures[0].getMessage()

    await conversation.arefresh_from_db()
    assert conversation.collection_id is None
    await attachment.arefresh_from_db()
    assert attachment.is_indexed is False
    assert attachment.rag_document_id is None


@pytest.mark.asyncio
async def test_reindex_continues_on_individual_attachment_failure(caplog):
    """Failure on one attachment doesn't abort the loop; collection_id is saved."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="first.md",
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="second.md",
    )

    mock_store = MagicMock()
    mock_store.collection_id = "col-789"
    mock_store.acreate_collection = AsyncMock()

    mock_to_thread = AsyncMock(side_effect=[RuntimeError("store_document failed"), None])

    mock_backend = MagicMock(return_value=mock_store)

    caplog.set_level(logging.ERROR, logger=REINDEXER_LOGGER)
    with (
        patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", side_effect=mock_to_thread),
    ):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)

    assert mock_to_thread.call_count == 2  # both attachments attempted
    assert isinstance(events[-1], events_v4.ToolResultPart)
    assert events[-1].result["state"] == "partial"
    assert "first.md" in events[-1].result["failed_documents"]

    attachment_failures = [
        r for r in caplog.records if "Failed to re-index attachment" in r.getMessage()
    ]
    assert len(attachment_failures) == 1
    assert attachment_failures[0].levelno == logging.ERROR
    assert attachment_failures[0].exc_info is not None

    await conversation.arefresh_from_db()
    assert conversation.collection_id == "col-789"
    assert conversation.index_state == CollectionIndexState.ERROR


@pytest.mark.asyncio
async def test_reindex_skips_binary_attachments():
    """Binary attachments (PDF, etc.) are filtered out; only text/* attachments are stored."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="application/pdf",
        file_name="doc.pdf",
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="doc.md",
    )

    mock_store = MagicMock()
    mock_store.collection_id = "col-abc"
    mock_store.acreate_collection = AsyncMock()

    mock_backend = MagicMock(return_value=mock_store)

    to_thread_calls = []

    async def capture_to_thread(func, *args, **kwargs):
        to_thread_calls.append(func)

    with (
        patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", side_effect=capture_to_thread),
    ):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)

    # Only the text/markdown attachment triggers store_document; PDF is skipped
    assert len(to_thread_calls) == 1
    assert to_thread_calls[0] == mock_store.store_document
    assert mock_store.parse_and_store_document.call_count == 0

    assert isinstance(events[-1], events_v4.ToolResultPart)
    assert events[-1].result == {"state": "done"}


@pytest.mark.asyncio
async def test_reindex_skips_in_context_attachments():
    """Attachments whose IDs are in in_context_ids (full-context) are not reindexed."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    att = await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
    )

    events = []
    async for event in reindex_conversation(conversation, in_context_ids={str(att.id)}):
        events.append(event)

    assert not events
    await conversation.arefresh_from_db()
    assert conversation.collection_id is None


@pytest.mark.asyncio
async def test_reindex_only_reindexes_out_of_context_attachments():
    """Only attachments absent from in_context_ids are stored."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    in_ctx_att = await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="small.md",
    )
    _ = await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="large.md",
    )

    mock_store = MagicMock()
    mock_store.collection_id = "col-xyz"
    mock_store.acreate_collection = AsyncMock()

    mock_backend = MagicMock(return_value=mock_store)

    to_thread_calls = []

    async def capture_to_thread(func, *args, **kwargs):
        to_thread_calls.append(func)

    with (
        patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", side_effect=capture_to_thread),
    ):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids={str(in_ctx_att.id)}):
            events.append(event)

    # Only the out-of-context attachment is stored
    assert len(to_thread_calls) == 1
    assert to_thread_calls[0] == mock_store.store_document

    assert isinstance(events[-1], events_v4.ToolResultPart)
    assert events[-1].result == {"state": "done"}

    await conversation.arefresh_from_db()
    assert conversation.collection_id == "col-xyz"


@pytest.mark.asyncio
async def test_concurrent_reindex_only_creates_one_collection():
    """Two concurrent resumes on the same de-indexed conversation create only one collection.

    asyncio.Barrier forces both coroutines to the claim step simultaneously so the
    race window is deterministic.
    """
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
    )

    create_calls = 0

    async def counting_create(*args, **kwargs):
        nonlocal create_calls
        create_calls += 1

    mock_store = MagicMock()
    mock_store.collection_id = "col-123"
    mock_store.acreate_collection = counting_create

    barrier = asyncio.Barrier(2)

    async def attempt():
        await barrier.wait()  # both tasks reach the claim step simultaneously
        async for _ in reindex_conversation(conversation, set()):
            pass

    with (
        patch(
            "chat.clients.conversation_reindexer.document_store_backend",
            MagicMock(return_value=mock_store),
        ),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", new=AsyncMock()),
    ):
        await asyncio.gather(attempt(), attempt())

    assert create_calls == 1
    await conversation.arefresh_from_db()
    assert conversation.collection_id == "col-123"


@pytest.mark.asyncio
async def test_reindex_existing_and_new_attachment_creates_single_collection():
    """New file added on resume is indexed in the same collection as existing deindexed files."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    # Two existing attachments reset by the deindex command
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="existing1.md",
        is_indexed=False,
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="existing2.md",
        is_indexed=False,
    )
    # New file added by the user when resuming (never indexed)
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="new.md",
        is_indexed=False,
    )

    mock_store = MagicMock()
    mock_store.collection_id = "col-resume"
    mock_store.acreate_collection = AsyncMock()

    mock_backend = MagicMock(return_value=mock_store)

    to_thread_calls = []

    async def capture_to_thread(func, *args, **kwargs):
        to_thread_calls.append(func)

    with (
        patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", side_effect=capture_to_thread),
    ):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)

    # Exactly one collection created for all three files
    mock_store.acreate_collection.assert_called_once()
    # All three attachments stored in that collection
    assert len(to_thread_calls) == 3
    assert all(func == mock_store.store_document for func in to_thread_calls)

    assert isinstance(events[-1], events_v4.ToolResultPart)
    assert events[-1].result == {"state": "done"}

    await conversation.arefresh_from_db()
    assert conversation.collection_id == "col-resume"
    assert conversation.index_state == CollectionIndexState.INDEXED


@pytest.mark.asyncio
async def test_reindex_yields_nothing_when_indexing_in_progress():
    """Busy-error events emitted when another process holds a fresh INDEXING claim."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(
        index_state=CollectionIndexState.INDEXING,
    )
    await conversation.arefresh_from_db()
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
    )

    events = []
    async for event in reindex_conversation(conversation, in_context_ids=set()):
        events.append(event)

    tool_call = next((e for e in events if isinstance(e, events_v4.ToolCallPart)), None)
    tool_result = next((e for e in events if isinstance(e, events_v4.ToolResultPart)), None)
    finish = next((e for e in events if isinstance(e, events_v4.FinishMessagePart)), None)
    assert tool_call is not None
    assert tool_call.tool_name == "document_parsing"
    assert tool_result is not None
    assert tool_result.result["kind"] == "concurrent_reindex"
    assert finish is not None
    assert finish.finish_reason == events_v4.FinishReason.ERROR
    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXING


@pytest.mark.asyncio
async def test_reindex_all_failures_sets_error_and_saves_collection_id():
    """When all attachments fail, index_state=ERROR and collection_id is saved (for retry reuse)."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="fail.md",
    )

    mock_store = MagicMock()
    mock_store.collection_id = "col-new"
    mock_store.acreate_collection = AsyncMock()
    mock_backend = MagicMock(return_value=mock_store)

    with (
        patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", new=AsyncMock(side_effect=RuntimeError("backend down"))),
    ):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)

    assert len(events) == 2
    assert isinstance(events[-1], events_v4.ToolResultPart)
    assert events[-1].result["state"] == "error"
    # RuntimeError is a non-HTTP exception → generic rag_error bucket
    assert events[-1].result["kind"] == "rag_error"

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR
    assert conversation.collection_id == "col-new"


def _http_error(status_code: int) -> requests.HTTPError:
    """Build a requests.HTTPError whose response carries the given status code."""
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


async def _run_reindex_with_collection_failure(conversation, exc):
    """Drive reindex_conversation with acreate_collection patched to raise `exc`."""
    mock_store = MagicMock()
    mock_store.collection_id = None
    mock_store.acreate_collection = AsyncMock(side_effect=exc)
    mock_backend = MagicMock(return_value=mock_store)
    with patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)
    return events


@pytest.mark.asyncio
async def test_reindex_collection_create_500_emits_rag_unavailable():
    """A 500 from acreate_collection surfaces as kind=rag_unavailable on the tool result."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
    )

    events = await _run_reindex_with_collection_failure(conversation, _http_error(500))

    tool_result = next(e for e in events if isinstance(e, events_v4.ToolResultPart))
    assert tool_result.result["state"] == "error"
    assert tool_result.result["kind"] == "rag_unavailable"

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR


@pytest.mark.asyncio
async def test_reindex_all_failures_uses_last_failure_kind_in_result(caplog):
    """When every attachment fails with different errors, result.kind is the LAST kind."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="first.md",
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        file_name="second.md",
    )

    mock_store = MagicMock()
    mock_store.collection_id = "col-mix"
    mock_store.acreate_collection = AsyncMock()
    mock_backend = MagicMock(return_value=mock_store)

    # First attachment: generic RuntimeError → rag_error.
    # Second attachment: httpx.ConnectError → rag_connection_error.
    # The aggregate result must carry rag_connection_error (the LAST kind).
    mock_to_thread = AsyncMock(side_effect=[RuntimeError("boom"), httpx.ConnectError("no route")])

    caplog.set_level(logging.ERROR, logger=REINDEXER_LOGGER)
    with (
        patch("chat.clients.conversation_reindexer.document_store_backend", mock_backend),
        patch(
            "chat.clients.conversation_reindexer._read_attachment_bytes",
            new=AsyncMock(return_value=b"data"),
        ),
        patch("asyncio.to_thread", side_effect=mock_to_thread),
    ):
        events = []
        async for event in reindex_conversation(conversation, in_context_ids=set()):
            events.append(event)

    tool_result = next(e for e in events if isinstance(e, events_v4.ToolResultPart))
    assert tool_result.result["state"] == "error"
    assert tool_result.result["kind"] == "rag_connection_error"

    attachment_failures = [
        r for r in caplog.records if "Failed to re-index attachment" in r.getMessage()
    ]
    assert len(attachment_failures) == 2
    assert all(r.levelno == logging.ERROR for r in attachment_failures)
    assert all(r.exc_info is not None for r in attachment_failures)

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR
    assert conversation.collection_id == "col-mix"


@pytest.mark.asyncio
async def test_reindex_collection_create_httpx_connect_emits_rag_connection_error():
    """An httpx.ConnectError from acreate_collection surfaces as kind=rag_connection_error."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id=None, index_state=CollectionIndexState.DEINDEXED
    )
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
    )

    events = await _run_reindex_with_collection_failure(
        conversation, httpx.ConnectError("no route")
    )

    tool_result = next(e for e in events if isinstance(e, events_v4.ToolResultPart))
    assert tool_result.result["state"] == "error"
    assert tool_result.result["kind"] == "rag_connection_error"
