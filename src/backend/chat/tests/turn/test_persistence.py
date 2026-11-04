"""Tests for the messages chat.turn.persistence.prepare_update_conversation stores."""

from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

from chat.turn.persistence import prepare_update_conversation
from chat.turn.usage import AgentUsage

USAGE = AgentUsage(prompt_tokens=10, completion_tokens=5)


@pytest.fixture(name="conversation")
def conversation_fixture():
    """Return a minimal mock conversation (no DB required)."""
    conv = MagicMock()
    conv.messages = []
    conv.pydantic_messages = []
    conv.agent_usage = {}
    return conv


def test_stores_the_rebuilt_user_message(conversation):
    """The user bubble is rebuilt from the request the agent ran on."""
    prepare_update_conversation(
        conversation,
        final_output=[
            ModelRequest(parts=[UserPromptPart(content="Hello?")], kind="request"),
            ModelResponse(parts=[TextPart(content="Hi!")], kind="response"),
        ],
        usage=USAGE,
        model_response_message_id="msg-1",
        is_truncated=False,
        question_stored=False,
    )

    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello?"),
        ("assistant", "Hi!"),
    ]


def test_stores_no_user_message_when_the_request_has_nothing_to_render(conversation):
    """A request the UI cannot render is skipped, not stored as an empty message."""
    prepare_update_conversation(
        conversation,
        final_output=[
            ModelRequest(parts=[SystemPromptPart(content="You are a bot")], kind="request"),
            ModelResponse(parts=[TextPart(content="Hi!")], kind="response"),
        ],
        usage=USAGE,
        model_response_message_id="msg-1",
        is_truncated=False,
        question_stored=False,
    )

    assert [(message.role, message.content) for message in conversation.messages] == [
        ("assistant", "Hi!")
    ]
