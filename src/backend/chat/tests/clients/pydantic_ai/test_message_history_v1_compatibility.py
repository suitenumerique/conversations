"""Conversations persisted by pydantic-ai 1.x must still load under 2.x.

`ChatConversation.pydantic_messages` stores `ModelMessagesTypeAdapter.dump_json()`
output. Rows written before the 2.x upgrade stay in the database untouched, so every
shape we ever wrote has to keep validating. The fixture was produced by running
`ModelMessagesTypeAdapter.dump_json()` under pydantic-ai 1.107.1 (the last 1.x
release) - do not regenerate it with the current version, that would defeat its
purpose.
"""

import json
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

FIXTURES_DIR = Path(__file__).parent / "fixtures"
V1_HISTORY = json.loads((FIXTURES_DIR / "pydantic_ai_v1_message_history.json").read_text())

# A run validates the history it is handed and drops leading messages it cannot repair.
# Only `synthetic_ok_response` is affected: the fixture opens on a tool return whose
# matching tool call is not part of the slice, so that first message never reaches the
# model. Everything after it is forwarded untouched.
LEADING_MESSAGES_REPAIRED_AWAY = {"synthetic_ok_response": 1}


def _load(case_name):
    return ModelMessagesTypeAdapter.validate_python(V1_HISTORY[case_name])


@pytest.mark.parametrize("case_name", list(V1_HISTORY))
def test_v1_history_validates(case_name):
    """Every persisted 1.x shape still validates under the current version."""
    messages = _load(case_name)

    assert messages
    assert all(isinstance(message, (ModelRequest, ModelResponse)) for message in messages)


@pytest.mark.parametrize("case_name", list(V1_HISTORY))
def test_v1_history_round_trips(case_name):
    """Re-dumping a loaded 1.x history and re-validating it is stable."""
    messages = _load(case_name)

    redumped = json.loads(ModelMessagesTypeAdapter.dump_json(messages))

    assert ModelMessagesTypeAdapter.validate_python(redumped) == messages


def test_v1_text_only_content_survives():
    """A plain exchange keeps its prompt, answer, instructions and usage details."""
    request, response = _load("text_only")

    assert request.instructions == "You are a helpful assistant."
    assert request.parts[0].content == "Bonjour"
    assert response.parts[0].content == "Bonjour !"
    assert response.model_name == "albert-large"
    # The CO2 accounting reads this back out of the persisted usage details.
    assert response.usage.details["co2_impact_factor_20"] == 730


def test_v1_tool_return_metadata_survives():
    """The RAG `sources` metadata attached to tool returns is preserved."""
    messages = _load("tool_call_with_sources_metadata")

    tool_call = messages[1].parts[0]
    tool_return = messages[2].parts[0]

    assert isinstance(tool_call, ToolCallPart)
    assert tool_call.tool_name == "document_search_rag"
    assert isinstance(tool_return, ToolReturnPart)
    assert tool_return.tool_call_id == tool_call.tool_call_id
    assert tool_return.metadata == {
        "sources": [{"document_name": "rapport.md", "chunk_id": 7, "score": 0.82}]
    }


def test_v1_thinking_part_survives():
    """ThinkingPart is still a distinct part kind, not folded into the text."""
    _, response = _load("thinking")

    assert isinstance(response.parts[0], ThinkingPart)
    assert response.parts[0].content == "L'utilisateur veut une explication."
    assert isinstance(response.parts[1], TextPart)


def test_v1_media_content_survives():
    """Image/document URLs and binary content keep their part types."""
    request, _ = _load("media_content")

    content = request.parts[0].content

    assert content[0] == "Que vois-tu ?"
    assert isinstance(content[1], ImageUrl)
    assert content[1].identifier == "photo.png"
    assert isinstance(content[2], DocumentUrl)
    assert isinstance(content[3], BinaryContent)
    assert content[3].media_type == "image/png"


def test_v1_retry_prompt_survives():
    """A persisted retry keeps the tool name and call id it retries."""
    messages = _load("retry_prompt")

    retry = messages[2].parts[0]

    assert isinstance(retry, RetryPromptPart)
    assert retry.tool_name == "get_weather"
    assert retry.tool_call_id == "call_r1"


def test_v1_synthetic_ok_response_survives():
    """The synthetic "ok" response inserted after a tool return still loads.

    See `AIAgentService._run_agent`: it appends a bare `ModelResponse` so Mistral
    never sees a user role directly after a tool role.
    """
    _, response = _load("synthetic_ok_response")

    assert response.parts[0].content == "ok"
    assert response.model_name is None


@pytest.mark.parametrize("case_name", list(V1_HISTORY))
@pytest.mark.asyncio
async def test_v1_history_is_usable_as_message_history(case_name):
    """A run forwards a 1.x-persisted history to the model, then the new prompt."""
    history = _load(case_name)
    sent = []

    def _reply(messages, _info):
        sent.append(messages)
        return ModelResponse(parts=[TextPart(content="Suite.")])

    agent = Agent(FunctionModel(_reply), output_type=str)

    result = await agent.run("Et ensuite ?", message_history=history)

    assert result.output == "Suite."
    # Asserted outside `_reply` so a failure surfaces as itself, not as a model error.
    forwarded = sent[0]
    assert forwarded[-1].parts[-1].content == "Et ensuite ?"
    assert forwarded[:-1] == history[LEADING_MESSAGES_REPAIRED_AWAY.get(case_name, 0) :]
