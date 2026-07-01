"""Tests for the INDEXING busy-state guard in _run_agent / reindex_conversation
and the error emission of `_handle_input_documents` on document rejection."""
# pylint: disable=protected-access

import logging
from datetime import timedelta

from django.utils import timezone

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import BinaryContent, DocumentUrl

from chat import models as chat_models
from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import DOCUMENT_URL_PREFIX, AIAgentService
from chat.enums import CollectionIndexState
from chat.factories import ChatConversationFactory
from chat.vercel_ai_sdk.core import events_v4

PYDANTIC_AI_LOGGER = "chat.clients.pydantic_ai"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True, name="base_settings")
def base_settings_fixture(settings):
    """Minimum LLM settings to instantiate AIAgentService."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []
    settings.REINDEX_CLAIM_TIMEOUT_SECONDS = 600


_USER_MESSAGE = [
    UIMessage(
        id="msg-1",
        role="user",
        content="Hello",
        parts=[TextUIPart(type="text", text="Hello, how are you?")],
    )
]


async def _run(service):
    """Collect all events, tolerating LLM errors that occur after the guard."""
    events = []
    try:
        async for event in service._run_agent(_USER_MESSAGE):
            events.append(event)
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001
        pass
    return events


@pytest.mark.asyncio
async def test_busy_error_emitted_when_indexing():
    """index_state=INDEXING (fresh claim held by another request) → busy error emitted."""
    conversation = await sync_to_async(ChatConversationFactory)(
        index_state=CollectionIndexState.INDEXING,
        collection_id="col-being-rebuilt",
    )
    service = AIAgentService(conversation, user=conversation.owner)

    events = await _run(service)

    tool_call = next((e for e in events if isinstance(e, events_v4.ToolCallPart)), None)
    tool_result = next((e for e in events if isinstance(e, events_v4.ToolResultPart)), None)
    finish = next((e for e in events if isinstance(e, events_v4.FinishMessagePart)), None)

    assert tool_call is not None
    assert tool_call.tool_name == "document_parsing"
    assert tool_result is not None
    assert tool_result.result["state"] == "error"
    assert tool_result.result["kind"] == "concurrent_reindex"
    assert "retry" in tool_result.result["error"].lower()
    assert finish is not None
    assert finish.finish_reason == events_v4.FinishReason.ERROR


@pytest.mark.asyncio
async def test_no_busy_error_when_indexing_but_no_own_documents():
    """INDEXING with no collection_id → guard does not fire."""
    conversation = await sync_to_async(ChatConversationFactory)(
        index_state=CollectionIndexState.INDEXING,
        collection_id=None,
    )
    service = AIAgentService(conversation, user=conversation.owner)

    events = await _run(service)

    assert not any(
        isinstance(e, events_v4.FinishMessagePart)
        and e.finish_reason == events_v4.FinishReason.ERROR
        for e in events
    )


@pytest.mark.asyncio
async def test_no_busy_error_when_indexing_claim_timed_out():
    """INDEXING with expired claim → reindex_conversation reclaims it, no busy error."""
    conversation = await sync_to_async(ChatConversationFactory)(
        index_state=CollectionIndexState.INDEXING,
        collection_id="col-stale",
    )
    # Simulate a timed-out claim (updated_at older than REINDEX_CLAIM_TIMEOUT_SECONDS)
    await chat_models.ChatConversation.objects.filter(pk=conversation.pk).aupdate(
        updated_at=timezone.now() - timedelta(seconds=601)
    )
    await conversation.arefresh_from_db(fields=["updated_at"])
    service = AIAgentService(conversation, user=conversation.owner)

    events = await _run(service)

    assert not any(
        isinstance(e, events_v4.ToolResultPart)
        and isinstance(e.result, dict)
        and e.result.get("kind") == "concurrent_reindex"
        for e in events
    )


# --------------------------------------------------------------------------- #
# _handle_input_documents end-to-end error emission on document rejection
#
# Parsing moved to the worker, so the message-time handler no longer parses; it
# validates the current message's documents. A rejection must still emit the
# same error envelope it used to on a parse failure: a ToolResultPart error, a
# FinishMessagePart(ERROR), and a DocumentParsingResult(success=False), logged
# via logger.exception. Both reachable rejections classify as `rag_error` (only
# ValueError is raised here); the HTTP-derived kinds now happen on the worker and
# the kind mapping itself is unit-tested in test_error_classification.py.
# --------------------------------------------------------------------------- #


async def _collect_handle_input_documents(service, documents):
    """Run _handle_input_documents with the given documents and collect events."""
    usage = {"promptTokens": 0, "completionTokens": 0, "co2_impact": 0}
    events = []
    async for event in service._handle_input_documents(
        documents, conversation_has_own_documents=False, usage=usage
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "make_document",
    [
        pytest.param(
            lambda _conversation: BinaryContent(data=b"raw", media_type="text/plain"),
            id="inline-bytes",
        ),
        pytest.param(
            lambda _conversation: DocumentUrl(
                url=f"{DOCUMENT_URL_PREFIX}other-conversation/attachments/f.txt",
                media_type="text/plain",
            ),
            id="cross-conversation-url",
        ),
    ],
)
async def test_handle_input_documents_emits_error_envelope_on_rejection(make_document, caplog):
    """A rejected document emits the error envelope and aborts the turn, logged at ERROR."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    caplog.set_level(logging.ERROR, logger=PYDANTIC_AI_LOGGER)
    events = await _collect_handle_input_documents(service, [make_document(conversation)])

    # A document_parsing tool call is announced before the error result.
    tool_call = next(e for e in events if isinstance(e, events_v4.ToolCallPart))
    assert tool_call.tool_name == "document_parsing"

    tool_result = next(e for e in events if isinstance(e, events_v4.ToolResultPart))
    assert tool_result.result["state"] == "error"
    assert tool_result.result["kind"] == "rag_error"
    assert tool_result.result["error"]

    finish = next(e for e in events if isinstance(e, events_v4.FinishMessagePart))
    assert finish.finish_reason == events_v4.FinishReason.ERROR

    # The final marker reports failure so the caller aborts the turn.
    assert events[-1].success is False

    rejections = [r for r in caplog.records if "Rejected input documents" in r.getMessage()]
    assert len(rejections) == 1
    assert rejections[0].levelno == logging.ERROR
    # logger.exception attaches exc_info — a plain logger.error would not.
    assert rejections[0].exc_info is not None
    assert "rag_error" in rejections[0].getMessage()
