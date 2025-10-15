"""
Unit tests for the ChatConversationInputSerializer, covering validation of chat message input data.
"""

import datetime

import pytest
from rest_framework.exceptions import ErrorDetail

from chat import serializers
from chat.ai_sdk_types import (
    Attachment,
    LanguageModelV1Source,
    SourceUIPart,
    TextUIPart,
    ToolInvocationResult,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.llm_configuration import LLModel, LLMProvider


@pytest.fixture(name="llm_configuration")
def llm_configuration_fixture(settings):
    """
    Pytest fixture to configure LLM models for testing purposes.
    """
    settings.LLM_CONFIGURATIONS = {
        "model-1": LLModel(
            hrid="model-1",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon="base64encodediconstring",
            system_prompt="You are an amazing assistant.",
            tools=["web-search", "calculator"],
            provider=LLMProvider(hrid="unused", base_url="https://example.com", api_key="key"),
        ),
    }


def test_chat_conversation_input_serializer_no_message():
    """
    Ensure serializer fails validation if no messages are provided.
    """
    serializer = serializers.ChatConversationInputSerializer(data={})
    assert not serializer.is_valid()
    assert serializer.errors == {
        "messages": [ErrorDetail(string="This field is required.", code="required")]
    }


def test_chat_conversation_input_serializer_simple_message():
    """
    Ensure serializer validates a simple user message correctly.
    """
    _created_at = datetime.datetime(2020, 1, 1)

    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "yuPoOuBkKA4FnKvk",
                    "role": "user",
                    "parts": [{"text": "Hello", "type": "text"}],
                    "content": "Hello",
                    "createdAt": _created_at,
                }
            ]
        }
    )
    assert serializer.is_valid()
    assert serializer.validated_data == {
        "messages": [
            UIMessage(
                id="yuPoOuBkKA4FnKvk",
                createdAt=_created_at,
                content="Hello",
                reasoning=None,
                experimental_attachments=None,
                role="user",
                annotations=None,
                toolInvocations=None,
                parts=[TextUIPart(type="text", text="Hello")],
            )
        ]
    }


def test_chat_conversation_input_serializer_empty_messages():
    """
    Ensure serializer fails validation if the messages list is empty.
    """
    serializer = serializers.ChatConversationInputSerializer(data={"messages": []})
    assert not serializer.is_valid()
    assert serializer.errors == {
        "messages": [ErrorDetail(string="This list must not be empty.", code="invalid")]
    }


def test_chat_conversation_input_serializer_invalid_role():
    """
    Ensure serializer fails validation if the message role is invalid.
    """
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "1",
                    "role": "invalid_role",
                    "parts": [{"text": "Hello", "type": "text"}],
                    "content": "Hello",
                    "createdAt": "2025-07-03T15:22:17.105Z",
                }
            ]
        }
    )
    assert not serializer.is_valid()
    assert serializer.errors["messages"] == [
        {
            "ctx": {
                "expected": ErrorDetail(
                    string="'system', 'user', 'assistant' or 'data'", code="invalid"
                )
            },
            "input": ErrorDetail(string="invalid_role", code="invalid"),
            "loc": [
                ErrorDetail(string="0", code="invalid"),
                ErrorDetail(string="role", code="invalid"),
            ],
            "msg": ErrorDetail(
                string="Input should be 'system', 'user', 'assistant' or 'data'", code="invalid"
            ),
            "type": ErrorDetail(string="literal_error", code="invalid"),
            "url": ErrorDetail(
                string="https://errors.pydantic.dev/2.12/v/literal_error", code="invalid"
            ),
        }
    ]


def test_chat_conversation_input_serializer_invalid_created_at():
    """
    Ensure serializer fails validation if the createdAt field is not a valid date.
    """
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "1",
                    "role": "user",
                    "parts": [{"text": "Hello", "type": "text"}],
                    "content": "Hello",
                    "createdAt": "not-a-date",
                }
            ]
        }
    )
    assert not serializer.is_valid()
    assert serializer.errors["messages"] == [
        {
            "ctx": {"error": ErrorDetail(string="invalid character in year", code="invalid")},
            "input": ErrorDetail(string="not-a-date", code="invalid"),
            "loc": [
                ErrorDetail(string="0", code="invalid"),
                ErrorDetail(string="createdAt", code="invalid"),
            ],
            "msg": ErrorDetail(
                string="Input should be a valid datetime or date, invalid character in year",
                code="invalid",
            ),
            "type": ErrorDetail(string="datetime_from_date_parsing", code="invalid"),
            "url": ErrorDetail(
                string="https://errors.pydantic.dev/2.12/v/datetime_from_date_parsing",
                code="invalid",
            ),
        }
    ]


def test_chat_conversation_input_serializer_missing_parts():
    """
    Ensure serializer fails validation if the 'parts' field is missing from a message.
    """
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "1",
                    "role": "user",
                    "content": "Hello",
                    "createdAt": "2025-07-03T15:22:17.105Z",
                }
            ]
        }
    )
    assert not serializer.is_valid()
    assert serializer.errors["messages"] == [
        {
            "input": {
                "content": ErrorDetail(string="Hello", code="invalid"),
                "createdAt": ErrorDetail(string="2025-07-03T15:22:17.105Z", code="invalid"),
                "id": ErrorDetail(string="1", code="invalid"),
                "role": ErrorDetail(string="user", code="invalid"),
            },
            "loc": [
                ErrorDetail(string="0", code="invalid"),
                ErrorDetail(string="parts", code="invalid"),
            ],
            "msg": ErrorDetail(string="Field required", code="invalid"),
            "type": ErrorDetail(string="missing", code="invalid"),
            "url": ErrorDetail(string="https://errors.pydantic.dev/2.12/v/missing", code="invalid"),
        }
    ]


def test_chat_conversation_input_serializer_multiple_messages():
    """
    Ensure serializer validates correctly when multiple messages are provided.
    """
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "1",
                    "role": "user",
                    "parts": [{"text": "Hello", "type": "text"}],
                    "content": "Hello",
                    "createdAt": "2025-07-03T15:22:17.105Z",
                },
                {
                    "id": "2",
                    "role": "assistant",
                    "parts": [{"text": "Hi!", "type": "text"}],
                    "content": "Hi!",
                    "createdAt": "2025-07-03T15:23:00.000Z",
                },
            ]
        }
    )
    assert serializer.is_valid()
    assert len(serializer.validated_data["messages"]) == 2


def test_chat_conversation_input_serializer_invalid_parts_type():
    """
    Ensure serializer fails validation if a part has an invalid type.
    """
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "1",
                    "role": "user",
                    "parts": [{"text": "Hello", "type": "invalid_type"}],
                    "content": "Hello",
                    "createdAt": "2025-07-03T15:22:17.105Z",
                }
            ]
        }
    )
    assert not serializer.is_valid()
    # Don't test the full error content as it is too long...


def test_chat_conversation_input_serializer_missing_id():
    """
    Ensure serializer fails validation if the message id is missing.
    """
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "role": "user",
                    "parts": [{"text": "Hello", "type": "text"}],
                    "content": "Hello",
                    "createdAt": "2025-07-03T15:22:17.105Z",
                }
            ]
        }
    )
    assert not serializer.is_valid()
    assert serializer.errors["messages"] == [
        {
            "type": ErrorDetail(string="missing", code="invalid"),
            "loc": [
                ErrorDetail(string="0", code="invalid"),
                ErrorDetail(string="id", code="invalid"),
            ],
            "msg": ErrorDetail(string="Field required", code="invalid"),
            "input": {
                "role": ErrorDetail(string="user", code="invalid"),
                "parts": [
                    {
                        "text": ErrorDetail(string="Hello", code="invalid"),
                        "type": ErrorDetail(string="text", code="invalid"),
                    }
                ],
                "content": ErrorDetail(string="Hello", code="invalid"),
                "createdAt": ErrorDetail(string="2025-07-03T15:22:17.105Z", code="invalid"),
            },
            "url": ErrorDetail(string="https://errors.pydantic.dev/2.12/v/missing", code="invalid"),
        }
    ]


def test_chat_conversation_input_serializer_with_attachments():
    """
    Ensure serializer validates messages with attachments correctly.
    """
    _created_at = datetime.datetime.now()
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "7x3hLsq6rB3xp91T",
                    "role": "user",
                    "parts": [{"text": "How's the weather in this image?", "type": "text"}],
                    "content": "How's the weather in this image?",
                    "createdAt": _created_at,
                    "experimental_attachments": [
                        {
                            "url": ("data:image/png;base64,iVBORw0KGgoAAAAN..."),
                            "name": "weather.jpg",
                            "contentType": "image/png",
                        }
                    ],
                },
            ]
        }
    )
    assert serializer.is_valid()
    assert serializer.validated_data["messages"] == [
        UIMessage(
            id="7x3hLsq6rB3xp91T",
            createdAt=_created_at,
            content="How's the weather in this image?",
            reasoning=None,
            experimental_attachments=[
                Attachment(
                    name="weather.jpg",
                    contentType="image/png",
                    url="data:image/png;base64,iVBORw0KGgoAAAAN...",
                )
            ],
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="How's the weather in this image?")],
        )
    ]


def test_chat_conversation_input_serializer_with_source():
    """
    Ensure serializer validates messages with a source part correctly.
    """
    _created_at = datetime.datetime.now()
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "e7K0fIPCfsMHr72C",
                    "createdAt": _created_at,
                    "role": "user",
                    "content": "Qui est Jean Valjean ?",
                    "parts": [{"type": "text", "text": "Qui est Jean Valjean ?"}],
                },
                {
                    "id": "ni646jbPmW8fQ9zm",
                    "createdAt": _created_at,
                    "role": "assistant",
                    "content": "Jean Valjean est génial.",
                    "parts": [
                        {
                            "type": "source",
                            "source": {
                                "sourceType": "url",
                                "id": "c2b834e7-0cdf-4dfb-b0ce-4e0a50d0fa5a",
                                "url": "https://touslesjeans.example.com/",
                                "title": None,
                                "providerMetadata": {},
                            },
                        },
                        {"type": "text", "text": "Jean Valjean est génial."},
                    ],
                    "revisionId": "TpNWDkn988LyzItl",
                },
                {
                    "id": "JKiIRnWwFE9hL2Cb",
                    "createdAt": _created_at,
                    "role": "user",
                    "content": "Quel est son parcours ?",
                    "parts": [{"type": "text", "text": "Quel est son parcours ?"}],
                },
            ]
        }
    )

    assert serializer.is_valid()
    assert serializer.validated_data["messages"] == [
        UIMessage(
            id="e7K0fIPCfsMHr72C",
            createdAt=_created_at,
            content="Qui est Jean Valjean ?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="Qui est Jean Valjean ?")],
        ),
        UIMessage(
            id="ni646jbPmW8fQ9zm",
            createdAt=_created_at,
            content="Jean Valjean est génial.",
            reasoning=None,
            experimental_attachments=None,
            role="assistant",
            annotations=None,
            toolInvocations=None,
            parts=[
                SourceUIPart(
                    type="source",
                    source=LanguageModelV1Source(
                        sourceType="url",
                        id="c2b834e7-0cdf-4dfb-b0ce-4e0a50d0fa5a",
                        url="https://touslesjeans.example.com/",
                        title=None,
                        providerMetadata={},
                    ),
                ),
                TextUIPart(type="text", text="Jean Valjean est génial."),
            ],
        ),
        UIMessage(
            id="JKiIRnWwFE9hL2Cb",
            createdAt=_created_at,
            content="Quel est son parcours ?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="Quel est son parcours ?")],
        ),
    ]


def test_chat_conversation_input_serializer_with_tool():
    """
    Ensure serializer validates messages with a tool invocation part correctly.
    """
    _created_at = datetime.datetime.now()
    serializer = serializers.ChatConversationInputSerializer(
        data={
            "messages": [
                {
                    "id": "e7K0fIPCfsMHr72C",
                    "role": "user",
                    "parts": [{"text": "Weather in Paris?", "type": "text"}],
                    "content": "Weather in Paris?",
                    "createdAt": _created_at,
                },
                {
                    "id": "ni646jbPmW8fQ9zm",
                    "createdAt": _created_at,
                    "role": "assistant",
                    "content": "It beautiful.",
                    "parts": [
                        {
                            "type": "tool-invocation",
                            "toolInvocation": {
                                "toolCallId": "tool-invocation-id",
                                "toolName": "weather",
                                "args": {"location": "Paris, France"},
                                "state": "result",
                                "result": {"temperature": "25", "condition": "sunny"},
                            },
                        },
                    ],
                    "revisionId": "TpNWDkn988LyzItl",
                },
                {
                    "id": "JKiIRnWwFE9hL2Cb",
                    "createdAt": _created_at,
                    "role": "user",
                    "content": "Nice",
                    "parts": [{"type": "text", "text": "Nice"}],
                },
            ]
        }
    )

    assert serializer.is_valid()
    assert serializer.validated_data["messages"] == [
        UIMessage(
            id="e7K0fIPCfsMHr72C",
            createdAt=_created_at,
            content="Weather in Paris?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="Weather in Paris?")],
        ),
        UIMessage(
            id="ni646jbPmW8fQ9zm",
            createdAt=_created_at,
            content="It beautiful.",
            reasoning=None,
            experimental_attachments=None,
            role="assistant",
            annotations=None,
            toolInvocations=None,
            parts=[
                ToolInvocationUIPart(
                    type="tool-invocation",
                    toolInvocation=ToolInvocationResult(
                        toolCallId="tool-invocation-id",
                        toolName="weather",
                        args={"location": "Paris, France"},
                        result={"temperature": "25", "condition": "sunny"},
                        state="result",
                        step=None,
                    ),
                )
            ],
        ),
        UIMessage(
            id="JKiIRnWwFE9hL2Cb",
            createdAt=_created_at,
            content="Nice",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="Nice")],
        ),
    ]
