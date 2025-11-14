"""Unit tests for Langfuse tracing in AIAgentService."""

import pytest
import responses
from asgiref.sync import sync_to_async
from langfuse import Langfuse
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from core.factories import UserFactory

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


@pytest.fixture(name="langfuse_client", scope="function")
def langfuse_client_fixture():
    """Fixture to init langfuse for tests."""
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


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Set up base settings for the tests."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


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
    agent_model, ui_messages, settings, langfuse_client
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
        async for result in service.stream_text_async(ui_messages):
            results.append(result)

    # Verify that results were generated
    assert results == ["Hello! I'm doing well, thank you for asking."]

    langfuse_client.flush()

    # Verify Langfuse HTTP calls were made
    assert len(responses.calls) == 1
    assert (
        responses.calls[0].request.url == "https://langfuse.example.com/api/public/otel/v1/traces"
    )

    # quite complex to parse the full body, so just check that expected output is in there
    assert b"Hello! I'm doing well, thank you for asking." in responses.calls[0].request.body


@pytest.mark.asyncio
@responses.activate
async def test_langfuse_span_created_when_enabled_and_analytics_disabled(
    agent_model, ui_messages, settings, langfuse_client
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
        async for result in service.stream_text_async(ui_messages):
            results.append(result)

    # Verify that results were generated
    assert results == ["Hello! I'm doing well, thank you for asking."]

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
async def test_no_langfuse_span_when_disabled(agent_model, ui_messages, settings, langfuse_client):
    """Test Langfuse span is not created when Langfuse is disabled."""
    settings.LANGFUSE_ENABLED = False

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
        async for result in service.stream_text_async(ui_messages):
            results.append(result)

    # Verify that results were generated
    assert results == ["Hello! I'm doing well, thank you for asking."]

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
    # ConversationAgent should be created successfully
    assert service.conversation_agent is not None


@pytest.mark.asyncio
async def test_instrumentation_disabled_when_langfuse_disabled(settings):
    """Test service correctly sets flags when Langfuse is disabled."""
    # pylint: disable=protected-access
    settings.LANGFUSE_ENABLED = False

    user = await sync_to_async(UserFactory)(allow_conversation_analytics=True)
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)
    service = AIAgentService(conversation, user=user)

    # Verify that flags are set correctly
    assert service._langfuse_available is False
    assert service._store_analytics is False
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


def test_store_analytics_flag_when_langfuse_disabled(settings):
    """Test _store_analytics is False when Langfuse is disabled."""
    # pylint: disable=protected-access
    settings.LANGFUSE_ENABLED = False

    user = UserFactory(allow_conversation_analytics=True)
    conversation = ChatConversationFactory(owner=user)

    service = AIAgentService(conversation, user=user)
    assert service._langfuse_available is False
    assert service._store_analytics is False
