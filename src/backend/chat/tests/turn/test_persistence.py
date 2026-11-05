"""Tests for the messages chat.turn.persistence.prepare_update_conversation stores."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

from chat.agents.conversation import TitleGenerationAgent
from chat.turn.persistence import generate_title, prepare_update_conversation
from chat.turn.usage import AgentUsage

USAGE = AgentUsage(prompt_tokens=10, completion_tokens=5)

# A provider error body echoing the conversation, which must never reach the logs.
PROVIDER_BODY = "echoed secret conversation text"


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


@pytest.mark.asyncio
async def test_a_failed_title_logs_only_type_and_status(conversation, json_logs):
    """The title failure names the provider error by type and status, not its body."""
    conversation.pk = "c-1"
    conversation.messages = [MagicMock(role="user", content="Hello?")]
    error = ModelHTTPError(status_code=429, model_name="m", body=PROVIDER_BODY)

    with patch.object(TitleGenerationAgent, "run", new_callable=AsyncMock, side_effect=error):
        assert await generate_title(conversation, language="en") is None

    lines = json_logs()
    [line] = [line for line in lines if line["event"] == "title_generation_failed"]
    assert line["error_type"] == "ModelHTTPError"
    assert line["status_code"] == 429
    assert "error" not in line
    assert PROVIDER_BODY not in str(lines)
