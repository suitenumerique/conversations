"""Tests for the INDEXING busy-state guard in _run_agent / reindex_conversation."""
# pylint: disable=protected-access

from datetime import timedelta

from django.utils import timezone

import pytest
from asgiref.sync import sync_to_async

from chat import models as chat_models
from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.enums import CollectionIndexState
from chat.factories import ChatConversationFactory
from chat.vercel_ai_sdk.core import events_v4

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
