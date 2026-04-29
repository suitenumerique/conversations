"""Tests for ThinkingPart stripping based on model profile in AIAgentService."""

# pylint: disable=protected-access
import json
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    UserPromptPart,
)

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService, _strip_thinking_parts
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


def _response(*parts):
    """Helper to build a ModelResponse with given parts."""
    return ModelResponse(parts=list(parts))


def _request(*parts):
    """Helper to build a ModelRequest with given parts."""
    return ModelRequest(parts=list(parts))


@pytest.mark.parametrize(
    ("parts_in", "expected_parts"),
    [
        # strips ThinkingPart from a mixed response
        (
            [ThinkingPart(content="thinking..."), TextPart(content="answer")],
            [TextPart(content="answer")],
        ),
        # leaves response untouched when no ThinkingPart present
        (
            [TextPart(content="answer")],
            [TextPart(content="answer")],
        ),
        # strips ThinkingPart-only response, leaving empty parts list
        (
            [ThinkingPart(content="thinking...")],
            [],
        ),
    ],
    ids=["mixed_thinking_and_text", "text_only_unchanged", "thinking_only_emptied"],
)
def test_strip_thinking_parts(parts_in, expected_parts):
    """ThinkingPart is removed from ModelResponse; non-thinking parts are preserved."""
    result = _strip_thinking_parts([_response(*parts_in)])
    assert list(result[0].parts) == expected_parts


def test_strip_thinking_parts_mixed_history():
    """Only ModelResponse messages with ThinkingPart are modified; others are untouched."""
    request = _request(UserPromptPart(content="hello"))
    response_with_thinking = _response(
        ThinkingPart(content="thinking..."), TextPart(content="answer")
    )
    response_without_thinking = _response(TextPart(content="follow-up"))

    result = _strip_thinking_parts([request, response_with_thinking, response_without_thinking])

    assert result[0] is request
    assert list(result[1].parts) == [TextPart(content="answer")]
    assert result[2] is response_without_thinking


@pytest.fixture(autouse=True, name="base_settings")
def base_settings_fixture(settings):
    """Configure minimal LLM settings."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def _pydantic_messages_with_thinking():
    """Return pydantic_messages JSON with a ModelResponse containing a ThinkingPart."""
    messages = [
        ModelResponse(parts=[ThinkingPart(content="let me think"), TextPart(content="answer")])
    ]
    return json.loads(ModelMessagesTypeAdapter.dump_json(messages).decode())


def _mock_infer_model_profile(supports_thinking: bool):
    mock_model_profile = MagicMock()
    mock_model_profile.supports_thinking = supports_thinking
    return mock_model_profile


@pytest.mark.asyncio
async def test_thinking_parts_stripped_when_model_does_not_support_thinking():
    """When model profile.supports_thinking is False, ThinkingPart is removed from history."""
    conversation = await sync_to_async(ChatConversationFactory)(
        pydantic_messages=_pydantic_messages_with_thinking()
    )
    service = AIAgentService(conversation, user=conversation.owner)
    ui_message = UIMessage(
        id="msg-1", role="user", content="Hello", parts=[TextUIPart(type="text", text="Hello")]
    )

    with (
        patch(
            "chat.clients.pydantic_ai.infer_model_profile",
            return_value=_mock_infer_model_profile(supports_thinking=False),
        ),
        patch("chat.clients.pydantic_ai.update_history_local_urls", side_effect=lambda _conv, h: h),
    ):
        _, _, _, _, _, history, _ = await service._prepare_agent_run([ui_message])

    assert len(history) == 1
    assert isinstance(history[0], ModelResponse)
    assert not any(isinstance(p, ThinkingPart) for p in history[0].parts)
    assert any(isinstance(p, TextPart) for p in history[0].parts)


@pytest.mark.asyncio
async def test_thinking_parts_kept_when_model_supports_thinking():
    """When model profile.supports_thinking is True, ThinkingPart is preserved in history."""
    conversation = await sync_to_async(ChatConversationFactory)(
        pydantic_messages=_pydantic_messages_with_thinking()
    )
    service = AIAgentService(conversation, user=conversation.owner)
    ui_message = UIMessage(
        id="msg-1", role="user", content="Hello", parts=[TextUIPart(type="text", text="Hello")]
    )

    model_class = type(service.conversation_agent.model)
    with (
        patch.object(
            model_class,
            "profile",
            new_callable=PropertyMock,
            return_value=MagicMock(supports_thinking=True),
        ),
        patch("chat.clients.pydantic_ai.update_history_local_urls", side_effect=lambda _conv, h: h),
    ):
        _, _, _, _, _, history, _ = await service._prepare_agent_run([ui_message])

    assert len(history) == 1
    assert isinstance(history[0], ModelResponse)
    assert any(isinstance(p, ThinkingPart) for p in history[0].parts)
