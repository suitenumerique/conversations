"""Tests for the messages AIAgentService._prepare_update_conversation stores."""

# pylint: disable=protected-access
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

from chat.clients.pydantic_ai import AIAgentService
from chat.llm_configuration import LLModel

USAGE = {"promptTokens": 10, "completionTokens": 5, "co2_impact": 0}


@pytest.fixture(name="conversation")
def conversation_fixture():
    """Return a minimal mock conversation (no DB required)."""
    conv = MagicMock()
    conv.messages = []
    conv.pydantic_messages = []
    conv.agent_usage = {}
    return conv


@pytest.fixture(name="service")
def service_fixture(conversation):
    """Instantiate AIAgentService without __init__, injecting what the method needs."""
    service = object.__new__(AIAgentService)
    service.conversation = conversation
    service.user = SimpleNamespace(pk=1)
    service.conversation_agent = SimpleNamespace(
        configuration=LLModel(
            hrid="m",
            model_name="test:model",
            human_readable_name="M",
            is_active=True,
            system_prompt="hi",
            tools=[],
        )
    )
    return service


def test_stores_the_rebuilt_user_message(conversation, service):
    """The user bubble is rebuilt from the request the agent ran on."""
    service._prepare_update_conversation(
        final_output=[
            ModelRequest(parts=[UserPromptPart(content="Hello?")], kind="request"),
            ModelResponse(parts=[TextPart(content="Hi!")], kind="response"),
        ],
        usage=dict(USAGE),
        model_response_message_id="msg-1",
    )

    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello?"),
        ("assistant", "Hi!"),
    ]


def test_stores_no_user_message_when_the_request_has_nothing_to_render(conversation, service):
    """A request the UI cannot render is skipped, not stored as an empty message."""
    service._prepare_update_conversation(
        final_output=[
            ModelRequest(parts=[SystemPromptPart(content="You are a bot")], kind="request"),
            ModelResponse(parts=[TextPart(content="Hi!")], kind="response"),
        ],
        usage=dict(USAGE),
        model_response_message_id="msg-1",
    )

    assert [(message.role, message.content) for message in conversation.messages] == [
        ("assistant", "Hi!")
    ]
