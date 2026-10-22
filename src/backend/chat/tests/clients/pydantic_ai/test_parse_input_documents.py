"""Unit tests for AIAgentService._parse_input_documents."""
# pylint: disable=protected-access

from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from celery.exceptions import TimeoutError as CeleryTimeoutError
from pydantic_ai.messages import DocumentUrl

from core.file_upload.enums import AttachmentStatus

from chat.clients.pydantic_ai import DOCUMENT_URL_PREFIX, AIAgentService
from chat.enums import CollectionIndexState
from chat.factories import ChatConversationFactory
from chat.models import ChatConversationAttachment

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True, name="base_settings")
def base_settings_fixture(settings):
    """Minimum settings to instantiate AIAgentService."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def _mock_backend_class():
    """Backend class mock whose instance reports an already-created collection.

    The parse + store no longer runs through this backend (it moved to the Celery
    task); the web coroutine only uses it to decide whether to create a collection.
    """

    store = MagicMock()
    store.collection_id = "col-existing"
    return MagicMock(return_value=store)


def _mock_parse_task(rag_document_id, markdown_key=None):
    """Mock the parse task so `.delay(...).get()` returns a fixed parse result."""
    task = MagicMock()
    async_result = MagicMock()
    async_result.get.return_value = (markdown_key, rag_document_id)
    task.delay.return_value = async_result
    return task


def _mock_failing_parse_task(exception):
    """Mock the parse task so `.delay(...).get()` raises."""
    task = MagicMock()
    async_result = MagicMock()
    async_result.get.side_effect = exception
    task.delay.return_value = async_result
    return task


@pytest.mark.asyncio
async def test_index_state_set_to_indexed_when_rag_document_id_returned():
    """A successful parse marks the conversation INDEXED and records the markdown companion.

    The companion row points at the storage key the task wrote the parsed
    content to; the content itself never comes back through the result backend.
    """
    conversation = await sync_to_async(ChatConversationFactory)(collection_id="col-1")
    service = AIAgentService(conversation, user=conversation.owner)

    key = f"{conversation.pk}/attachments/file.pdf"
    document = DocumentUrl(url=f"{DOCUMENT_URL_PREFIX}{key}", media_type="application/pdf")
    with (
        patch("chat.clients.pydantic_ai.document_store_backend", _mock_backend_class()),
        patch(
            "chat.clients.pydantic_ai.parse_and_store_conversation_document_task",
            _mock_parse_task("doc-42", markdown_key=f"{key}.md"),
        ),
    ):
        await service._parse_input_documents([document])

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXED
    companion = await ChatConversationAttachment.objects.aget(conversion_from=key)
    assert companion.key == f"{key}.md"
    assert companion.upload_state == AttachmentStatus.READY


@pytest.mark.asyncio
async def test_index_state_not_saved_when_rag_document_id_is_none():
    """index_state must not change when the parse task returns no rag_document_id."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id="col-1",
        index_state=CollectionIndexState.DEINDEXED,
    )
    service = AIAgentService(conversation, user=conversation.owner)

    url = f"{DOCUMENT_URL_PREFIX}{conversation.pk}/attachments/file.txt"
    document = DocumentUrl(url=url, media_type="text/plain")
    with (
        patch("chat.clients.pydantic_ai.document_store_backend", _mock_backend_class()),
        patch(
            "chat.clients.pydantic_ai.parse_and_store_conversation_document_task",
            _mock_parse_task(None),
        ),
    ):
        await service._parse_input_documents([document])

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.DEINDEXED


@pytest.mark.asyncio
async def test_result_is_forgotten_when_parse_task_fails():
    """The result payload is dropped from the result backend even when the task fails.

    Otherwise the (possibly large) parsed content would linger in the result
    backend until `result_expires`.
    """
    conversation = await sync_to_async(ChatConversationFactory)(collection_id="col-1")
    service = AIAgentService(conversation, user=conversation.owner)

    url = f"{DOCUMENT_URL_PREFIX}{conversation.pk}/attachments/file.txt"
    document = DocumentUrl(url=url, media_type="text/plain")
    task = _mock_failing_parse_task(RuntimeError("parse exploded"))
    with (
        patch("chat.clients.pydantic_ai.document_store_backend", _mock_backend_class()),
        patch("chat.clients.pydantic_ai.parse_and_store_conversation_document_task", task),
        pytest.raises(RuntimeError, match="parse exploded"),
    ):
        await service._parse_input_documents([document])

    task.delay.return_value.forget.assert_called_once()


@pytest.mark.asyncio
async def test_task_is_revoked_when_result_wait_times_out():
    """A result-wait timeout revokes the task so a still-queued parse never runs.

    Without the revoke, a task stuck in the queue would execute after the user
    already saw the turn fail, storing chunks nothing references.
    """
    conversation = await sync_to_async(ChatConversationFactory)(collection_id="col-1")
    service = AIAgentService(conversation, user=conversation.owner)

    url = f"{DOCUMENT_URL_PREFIX}{conversation.pk}/attachments/file.txt"
    document = DocumentUrl(url=url, media_type="text/plain")
    task = _mock_failing_parse_task(CeleryTimeoutError("result wait timed out"))
    with (
        patch("chat.clients.pydantic_ai.document_store_backend", _mock_backend_class()),
        patch("chat.clients.pydantic_ai.parse_and_store_conversation_document_task", task),
        pytest.raises(CeleryTimeoutError, match="result wait timed out"),
    ):
        await service._parse_input_documents([document])

    task.delay.return_value.revoke.assert_called_once()
    task.delay.return_value.forget.assert_called_once()
