"""Unit tests for Langfuse tracing in AIAgentService."""

import asyncio
import json

from django.test import AsyncClient

import pytest
import responses
import sentry_sdk
from asgiref.sync import sync_to_async
from langfuse import Langfuse
from langfuse._client.resource_manager import LangfuseResourceManager
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from core.factories import UserFactory

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.tests.utils import stream_text

pytestmark = pytest.mark.django_db()


@pytest.fixture(name="langfuse_client", scope="module")
def langfuse_client_fixture():
    """Fixture to init langfuse for tests.

    Module-scoped: LangfuseResourceManager is a process-wide singleton keyed
    by public_key, and OpenTelemetry's global TracerProvider can only be set
    once per process. Re-constructing Langfuse(public_key="pk-test-key") in
    every test either resurrects a dead, shut-down singleton (hangs in
    flush()'s queue.join()) or, if evicted, ends up adding a duplicate span
    processor to the same global TracerProvider on each re-init (causing
    duplicate exports). Building it once per module and only shutting it down
    after the last test avoids both failure modes.
    """
    langfuse_client = Langfuse(
        public_key="pk-test-key",
        secret_key="sk-test-key",
        host="https://langfuse.example.com",
        environment="test",
        debug=True,
    )
    yield langfuse_client
    langfuse_client._resources.prompt_cache._task_manager.shutdown()  # pylint: disable=protected-access
    langfuse_client.shutdown()
    LangfuseResourceManager._instances.pop("pk-test-key", None)  # pylint: disable=protected-access


@pytest.fixture(autouse=True)
def mock_token_counter(monkeypatch):
    """Prevent tiktoken from making network calls during sliding window token estimation."""
    monkeypatch.setattr(
        "chat.agents.history_processors.count_approx_tokens",
        lambda _text: 10,
    )


@pytest.fixture(name="ui_messages")
def ui_messages_fixture():
    """Fixture for test UI messages."""
    return [
        UIMessage(
            id="msg-1",
            role="user",
            content="Hello, how are you?",
            parts=[TextUIPart(type="text", text="Hello, how are you?")],
        )
    ]


@pytest.fixture(name="agent_model")
def agent_model_fixture():
    """Fixture for agent model function."""

    async def _agent_model(_messages: list[ModelMessage], _info: AgentInfo):
        """Simple agent model that returns a fixed response."""
        yield "Hello! I'm doing well, thank you for asking."

    return FunctionModel(stream_function=_agent_model)


@pytest.mark.asyncio
@responses.activate
async def test_langfuse_span_created_when_enabled_and_analytics_allowed(
    agent_model,
    ui_messages,
    settings,
    langfuse_client,
):
    """Test Langfuse span is created when enabled and user allows analytics."""
    settings.LANGFUSE_ENABLED = True

    # Mock Langfuse HTTP endpoints
    responses.add(
        responses.POST,
        "https://langfuse.example.com/api/public/otel/v1/traces",
        json={"success": True},
        status=200,
    )

    # Create user with analytics enabled
    user = await sync_to_async(UserFactory)(allow_conversation_analytics=True)
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)

    service = AIAgentService(conversation, user=user)
    results = []
    with service.conversation_agent.override(model=agent_model):
        async for result in service.stream_data_async(ui_messages):
            results.append(result)

    # Verify that results were generated
    assert stream_text(results) == "Hello! I'm doing well, thank you for asking."

    langfuse_client.flush()

    # Verify Langfuse HTTP calls were made
    assert len(responses.calls) == 1
    assert (
        responses.calls[0].request.url == "https://langfuse.example.com/api/public/otel/v1/traces"
    )

    # quite complex to parse the full body, so just check that expected output is in there
    body = responses.calls[0].request.body
    assert b"Hello! I'm doing well, thank you for asking." in body
    # v4: trace-level attributes are propagated via `propagate_attributes`
    assert str(user.sub).encode() in body
    assert str(conversation.pk).encode() in body
    assert user.email.split("@")[-1].encode() in body
    # v4: the conversation span is created via `start_as_current_observation`
    assert b"conversation" in body


@pytest.mark.asyncio
@responses.activate
async def test_langfuse_span_created_when_enabled_and_analytics_disabled(
    agent_model,
    ui_messages,
    settings,
    langfuse_client,
):
    """Test Langfuse span is created even when user disallows analytics."""
    settings.LANGFUSE_ENABLED = True

    # Mock Langfuse HTTP endpoints
    responses.add(
        responses.POST,
        "https://langfuse.example.com/api/public/otel/v1/traces",
        json={"success": True},
        status=200,
    )

    # Create user with analytics disabled
    user = await sync_to_async(UserFactory)(allow_conversation_analytics=False)
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)

    service = AIAgentService(conversation, user=user)
    results = []
    with service.conversation_agent.override(model=agent_model):
        async for result in service.stream_data_async(ui_messages):
            results.append(result)

    # Verify that results were generated
    assert stream_text(results) == "Hello! I'm doing well, thank you for asking."

    langfuse_client.flush()

    # Verify Langfuse HTTP calls were made
    assert len(responses.calls) == 1
    assert (
        responses.calls[0].request.url == "https://langfuse.example.com/api/public/otel/v1/traces"
    )

    # quite complex to parse the full body, so just check that expected output is in there
    assert b"Hello! I'm doing well, thank you for asking." not in responses.calls[0].request.body
    assert b"REDACTED" in responses.calls[0].request.body


@pytest.mark.asyncio
@responses.activate
async def test_no_langfuse_span_when_disabled(agent_model, ui_messages, langfuse_client):
    """Test Langfuse span is not created when Langfuse is disabled."""

    # Mock Langfuse HTTP endpoints (should not be called)
    responses.add(
        responses.POST,
        "https://langfuse.example.com/api/public/ingestion",
        json={"success": True},
        status=200,
    )

    user = await sync_to_async(UserFactory)(allow_conversation_analytics=True)
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)

    service = AIAgentService(conversation, user=user)
    results = []
    with service.conversation_agent.override(model=agent_model):
        async for result in service.stream_data_async(ui_messages):
            results.append(result)

    # Verify that results were generated
    assert stream_text(results) == "Hello! I'm doing well, thank you for asking."

    langfuse_client.flush()

    # Verify NO Langfuse HTTP calls were made
    assert len(responses.calls) == 0


@pytest.mark.asyncio
async def test_instrumentation_settings_with_analytics_enabled(settings):
    """Test service correctly sets flags when Langfuse and analytics are enabled."""
    # pylint: disable=protected-access
    settings.LANGFUSE_ENABLED = True

    user = await sync_to_async(UserFactory)(allow_conversation_analytics=True)
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)
    service = AIAgentService(conversation, user=user)

    # Verify that flags are set correctly
    assert service._langfuse_available is True
    assert service._store_analytics is True
    # v4: span is created lazily inside `_stream_content`
    assert service._langfuse_span is None
    # ConversationAgent should be created successfully
    assert service.conversation_agent is not None


@pytest.mark.asyncio
async def test_instrumentation_settings_with_analytics_disabled(settings):
    """Test service correctly sets flags when Langfuse enabled but analytics disabled."""
    # pylint: disable=protected-access
    settings.LANGFUSE_ENABLED = True

    user = await sync_to_async(UserFactory)(allow_conversation_analytics=False)
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)
    service = AIAgentService(conversation, user=user)

    # Verify that flags are set correctly
    assert service._langfuse_available is True
    assert service._store_analytics is False
    assert service._langfuse_span is None
    # ConversationAgent should be created successfully
    assert service.conversation_agent is not None


@pytest.mark.asyncio
async def test_instrumentation_disabled_when_langfuse_disabled():
    """Test service correctly sets flags when Langfuse is disabled."""
    # pylint: disable=protected-access

    user = await sync_to_async(UserFactory)(allow_conversation_analytics=True)
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)
    service = AIAgentService(conversation, user=user)

    # Verify that flags are set correctly
    assert service._langfuse_available is False
    assert service._store_analytics is False
    assert service._langfuse_span is None
    # ConversationAgent should be created successfully
    assert service.conversation_agent is not None


def test_store_analytics_flag_when_langfuse_enabled_and_user_allows(settings):
    """Test _store_analytics is True when Langfuse enabled and user allows analytics."""
    # pylint: disable=protected-access
    settings.LANGFUSE_ENABLED = True

    user = UserFactory(allow_conversation_analytics=True)
    conversation = ChatConversationFactory(owner=user)

    service = AIAgentService(conversation, user=user)
    assert service._langfuse_available is True
    assert service._store_analytics is True


def test_store_analytics_flag_when_langfuse_enabled_and_user_disallows(settings):
    """Test _store_analytics is False when Langfuse enabled but user disallows analytics."""
    # pylint: disable=protected-access
    settings.LANGFUSE_ENABLED = True

    user = UserFactory(allow_conversation_analytics=False)
    conversation = ChatConversationFactory(owner=user)

    service = AIAgentService(conversation, user=user)
    assert service._langfuse_available is True
    assert service._store_analytics is False


def test_store_analytics_flag_when_langfuse_disabled():
    """Test _store_analytics is False when Langfuse is disabled."""
    # pylint: disable=protected-access

    user = UserFactory(allow_conversation_analytics=True)
    conversation = ChatConversationFactory(owner=user)

    service = AIAgentService(conversation, user=user)
    assert service._langfuse_available is False
    assert service._store_analytics is False


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@responses.activate
async def test_a_turn_error_in_sentry_names_its_langfuse_trace(
    settings, monkeypatch, langfuse_client, sentry_events
):
    """Sentry tags the error with the request id, which is the turn's Langfuse trace id.

    Emulates Django's ASGI handler, which serves the response from a child task:
    the error surfaces in its parent, where Sentry captures it.
    """
    settings.LANGFUSE_ENABLED = True
    monkeypatch.setenv("PYTHON_SERVER_MODE", "async")
    responses.add(responses.POST, "https://langfuse.example.com/api/public/otel/v1/traces")

    async def failing_run(*_args, **_kwargs):
        raise RuntimeError("agent bug")
        yield  # pylint: disable=unreachable

    monkeypatch.setattr(AIAgentService, "_run_agent", failing_run)
    conversation = await sync_to_async(ChatConversationFactory)(owner__language="en-us")
    client = AsyncClient()
    await client.aforce_login(conversation.owner)
    request_id = "634ab47a476a56b0d7d0503950605134"
    chunks = []

    async def serve():
        response = await client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            {
                "messages": [
                    {"id": "m-1", "role": "user", "parts": [{"type": "text", "text": "Hi"}]}
                ]
            },
            content_type="application/json",
            headers={"X-Request-ID": request_id},
        )
        async for chunk in response.streaming_content:
            chunks.append(chunk)

    with sentry_sdk.isolation_scope():
        try:
            await asyncio.create_task(serve())
        except RuntimeError as exc:
            sentry_sdk.capture_exception(exc)

    # The other event is django-structlog's `streaming_failed` line, ignored in production
    [event] = [event for event in sentry_events if "logentry" not in event]
    assert event["tags"]["request_id"] == request_id
    assert event["tags"]["conversation_id"] == str(conversation.pk)
    start = json.loads(chunks[0].decode().removeprefix("data: "))
    assert start["messageId"] == f"trace-{request_id}"
    langfuse_client.flush()
    assert bytes.fromhex(request_id) in responses.calls[0].request.body
