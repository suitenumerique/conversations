"""Tests for AIAgentService._reindex_conversation method."""

# pylint: disable=protected-access
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from core.file_upload.enums import AttachmentStatus

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.vercel_ai_sdk.core import events_v4

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Set up base settings for the tests."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


@pytest.mark.asyncio
async def test_reindex_emits_events_and_saves_collection_id():
    """Re-indexing emits ToolCallPart + ToolResultPart and saves collection_id."""
    conversation = await sync_to_async(ChatConversationFactory)(collection_id=None)
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

    service = AIAgentService(conversation, user=conversation.owner)

    mock_store = MagicMock()
    mock_store.collection_id = "new-456"
    mock_store.acreate_collection = AsyncMock()

    mock_backend = MagicMock(return_value=mock_store)

    fake_file = MagicMock()
    fake_file.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"data")))
    fake_file.__exit__ = MagicMock(return_value=False)

    to_thread_calls = []

    async def capture_to_thread(func, *args, **kwargs):
        to_thread_calls.append(func)

    with (
        patch("chat.clients.pydantic_ai.document_store_backend", mock_backend),
        patch("django.core.files.storage.default_storage.open", return_value=fake_file),
        patch("asyncio.to_thread", side_effect=capture_to_thread),
    ):
        events = []
        async for event in service._reindex_conversation():
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
    conversation = await sync_to_async(ChatConversationFactory)(collection_id=None)
    # Create one attachment in a non-READY state
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.PENDING,
    )

    service = AIAgentService(conversation, user=conversation.owner)

    events = []
    async for event in service._reindex_conversation():
        events.append(event)

    assert not events
    assert conversation.collection_id is None


@pytest.mark.asyncio
async def test_reindex_yields_error_event_on_collection_creation_failure():
    """Error event is yielded when acreate_collection raises, collection_id stays None."""
    conversation = await sync_to_async(ChatConversationFactory)(collection_id=None)
    await sync_to_async(ChatConversationAttachmentFactory)(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
    )

    service = AIAgentService(conversation, user=conversation.owner)

    mock_store = MagicMock()
    mock_store.collection_id = None
    mock_store.acreate_collection = AsyncMock(side_effect=RuntimeError("Albert down"))
    mock_backend = MagicMock(return_value=mock_store)

    with patch("chat.clients.pydantic_ai.document_store_backend", mock_backend):
        events = []
        async for event in service._reindex_conversation():
            events.append(event)

    assert len(events) == 2
    assert isinstance(events[0], events_v4.ToolCallPart)
    assert events[0].tool_name == "conversation_resume"
    assert isinstance(events[1], events_v4.ToolResultPart)
    assert events[1].result["state"] == "error"

    assert conversation.collection_id is None


@pytest.mark.asyncio
async def test_reindex_continues_on_individual_attachment_failure():
    """Failure on one attachment doesn't abort the loop; collection_id is saved."""
    conversation = await sync_to_async(ChatConversationFactory)(collection_id=None)
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

    service = AIAgentService(conversation, user=conversation.owner)

    mock_store = MagicMock()
    mock_store.collection_id = "col-789"
    mock_store.acreate_collection = AsyncMock()

    mock_to_thread = AsyncMock(side_effect=[OSError("storage read failed"), "parsed"])

    fake_file = MagicMock()
    fake_file.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"data")))
    fake_file.__exit__ = MagicMock(return_value=False)

    mock_backend = MagicMock(return_value=mock_store)

    with (
        patch("chat.clients.pydantic_ai.document_store_backend", mock_backend),
        patch("django.core.files.storage.default_storage.open", return_value=fake_file),
        patch("asyncio.to_thread", side_effect=mock_to_thread),
    ):
        events = []
        async for event in service._reindex_conversation():
            events.append(event)

    assert mock_to_thread.call_count == 2  # both attachments attempted
    assert isinstance(events[-1], events_v4.ToolResultPart)
    assert events[-1].result["state"] == "partial"
    assert "first.md" in events[-1].result["failed_documents"]

    await conversation.arefresh_from_db()
    assert conversation.collection_id == "col-789"


@pytest.mark.asyncio
async def test_reindex_skips_binary_attachments():
    """Binary attachments (PDF, etc.) are skipped; only text/* attachments are stored."""
    conversation = await sync_to_async(ChatConversationFactory)(collection_id=None)
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

    service = AIAgentService(conversation, user=conversation.owner)

    mock_store = MagicMock()
    mock_store.collection_id = "col-abc"
    mock_store.acreate_collection = AsyncMock()

    mock_backend = MagicMock(return_value=mock_store)

    fake_file = MagicMock()
    fake_file.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"data")))
    fake_file.__exit__ = MagicMock(return_value=False)

    to_thread_calls = []

    async def capture_to_thread(func, *args, **kwargs):
        to_thread_calls.append(func)

    with (
        patch("chat.clients.pydantic_ai.document_store_backend", mock_backend),
        patch("django.core.files.storage.default_storage.open", return_value=fake_file),
        patch("asyncio.to_thread", side_effect=capture_to_thread),
    ):
        events = []
        async for event in service._reindex_conversation():
            events.append(event)

    # Only the text/markdown attachment triggers store_document; PDF is skipped
    assert len(to_thread_calls) == 1
    assert to_thread_calls[0] == mock_store.store_document
    assert mock_store.parse_and_store_document.call_count == 0

    assert isinstance(events[-1], events_v4.ToolResultPart)
    assert events[-1].result == {"state": "done"}
