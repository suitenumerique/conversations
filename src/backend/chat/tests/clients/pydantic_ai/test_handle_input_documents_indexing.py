"""Tests for the INDEXING busy-state guard in _run_agent / reindex_conversation."""
# pylint: disable=protected-access

import logging
from datetime import timedelta
from unittest.mock import AsyncMock

from django.utils import timezone

import pytest
import requests
from asgiref.sync import sync_to_async
from pydantic_ai.messages import BinaryContent

from chat import models as chat_models
from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
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
# _handle_input_documents end-to-end error classification
# --------------------------------------------------------------------------- #


def _http_error(status_code: int) -> requests.HTTPError:
    """Build a requests.HTTPError whose response carries the given status code."""
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


async def _collect_handle_input_documents(service, exc):
    """Run _handle_input_documents with a single document and a stubbed parse step."""
    service._parse_input_documents = AsyncMock(side_effect=exc)
    document = BinaryContent(data=b"hello", media_type="text/plain")
    usage = {"promptTokens": 0, "completionTokens": 0, "co2_impact": 0}
    events = []
    async for event in service._handle_input_documents(
        [document], conversation_has_own_documents=False, usage=usage
    ):
        events.append(event)
    return events


def _tool_result(events):
    return next(e for e in events if isinstance(e, events_v4.ToolResultPart))


@pytest.mark.asyncio
async def test_handle_input_documents_emits_rag_unavailable_on_500(caplog):
    """A 500 from the RAG backend surfaces as kind=rag_unavailable and is logged at ERROR."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    caplog.set_level(logging.ERROR, logger=PYDANTIC_AI_LOGGER)
    events = await _collect_handle_input_documents(service, _http_error(500))

    result = _tool_result(events).result
    assert result["state"] == "error"
    assert result["kind"] == "rag_unavailable"

    parse_failures = [
        r for r in caplog.records if "Error parsing input documents" in r.getMessage()
    ]
    assert len(parse_failures) == 1
    assert parse_failures[0].levelno == logging.ERROR
    # logger.exception attaches exc_info — a plain logger.error would not.
    assert parse_failures[0].exc_info is not None
    assert "rag_unavailable" in parse_failures[0].getMessage()


@pytest.mark.asyncio
async def test_handle_input_documents_emits_rag_connection_error_on_network_failure():
    """A requests.ConnectionError surfaces as kind=rag_connection_error."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    events = await _collect_handle_input_documents(service, requests.ConnectionError("no route"))

    result = _tool_result(events).result
    assert result["kind"] == "rag_connection_error"


@pytest.mark.asyncio
async def test_handle_input_documents_emits_generic_rag_error_on_local_failure():
    """A non-HTTP exception (e.g. local parser failure) surfaces as kind=rag_error."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    events = await _collect_handle_input_documents(service, ValueError("bad odt"))

    result = _tool_result(events).result
    assert result["kind"] == "rag_error"
