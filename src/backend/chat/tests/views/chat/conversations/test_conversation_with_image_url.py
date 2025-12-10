"""Unit tests for chat conversation actions with image URL."""

import uuid

from django.utils import timezone

import pytest
from dirty_equals import IsUUID
from freezegun import freeze_time
from pydantic_ai import ModelRequest, RequestUsage
from pydantic_ai.messages import (
    ImageUrl,
    ModelMessage,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from rest_framework import status

from chat.ai_sdk_types import (
    Attachment,
    TextUIPart,
    UIMessage,
)
from chat.factories import ChatConversationFactory
from chat.tests.utils import replace_uuids_with_placeholder

# enable database transactions for tests:
# transaction=True ensures that the data are available in the database
# in other threads
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Fixture to set AI service URLs for testing."""
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"
    return settings


@pytest.fixture(name="sample_image_content")
def fixture_sample_image_content():
    """Create a dummy image content as bytes."""
    # This is a simple, valid 1x1 PNG image content.
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9c\x63\x00"
        b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@freeze_time("2025-10-18T20:48:20.286204Z")
def test_post_conversation_with_local_image_url(
    api_client,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with an image URL.
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this image?",
        parts=[
            TextUIPart(
                text="What is in this image?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.png",
                contentType="image/png",
                url=image_url,
            )
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        presigned_url = messages[0].parts[3].content[1].url
        assert presigned_url.startswith("http://localhost:9000/conversations-media-storage/")
        assert presigned_url.find("X-Amz-Signature=") != -1
        assert presigned_url.find("X-Amz-Date=") != -1
        assert presigned_url.find("X-Amz-Expires=") != -1

        assert messages == [
            ModelRequest(
                parts=[
                    SystemPromptPart(
                        content="You are a helpful test assistant :)", timestamp=timezone.now()
                    ),
                    SystemPromptPart(
                        content="Today is Saturday 18/10/2025.", timestamp=timezone.now()
                    ),
                    SystemPromptPart(content="Answer in english.", timestamp=timezone.now()),
                    UserPromptPart(
                        content=[
                            "What is in this image?",
                            ImageUrl(
                                url=presigned_url,  # presigned URL for this conversation
                                media_type="image/png",
                                identifier="sample.png",
                            ),
                        ],
                        timestamp=timezone.now(),
                    ),
                ],
                run_id=messages[0].run_id,
            )
        ]
        yield "This is an image of a single pixel."

    # Use the fixture with FunctionModel
    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"This is an image of a single pixel."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":50,"completionTokens":9}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="What is in this image?",
        reasoning=None,
        experimental_attachments=[
            Attachment(name="sample.png", contentType="image/png", url=image_url)
        ],
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="What is in this image?"),
        ],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="This is an image of a single pixel.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is an image of a single pixel."),
        ],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": "You are a helpful test assistant :)",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
                {
                    "content": "Today is Saturday 18/10/2025.",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
                {
                    "content": "Answer in english.",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
                {
                    "content": [
                        "What is in this image?",
                        {
                            "force_download": False,
                            "identifier": "sample.png",
                            "kind": "image-url",
                            "media_type": "image/png",
                            "url": image_url,
                            "vendor_metadata": None,
                        },
                    ],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": None,
            "kind": "response",
            "model_name": "function::agent_model",
            "parts": [
                {"content": "This is an image of a single pixel.", "id": None, "part_kind": "text"}
            ],
            "provider_details": None,
            "provider_name": None,
            "provider_response_id": None,
            "timestamp": "2025-10-18T20:48:20.286204Z",
            "usage": {
                "cache_audio_read_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "details": {},
                "input_audio_tokens": 0,
                "input_tokens": 50,
                "output_audio_tokens": 0,
                "output_tokens": 9,
            },
            "run_id": _run_id,
        },
    ]


@freeze_time()
def test_post_conversation_with_local_image_wrong_url(
    api_client,
    today_promt_date,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a tampered URL.
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    image_url = f"/media-key/{uuid.uuid4()}/sample.png"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this image?",
        parts=[
            TextUIPart(
                text="What is in this image?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.png",
                contentType="image/png",
                url=image_url,
            )
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        assert messages == [
            ModelRequest(
                parts=[
                    SystemPromptPart(
                        content="You are a helpful test assistant :)", timestamp=timezone.now()
                    ),
                    SystemPromptPart(content=today_promt_date, timestamp=timezone.now()),
                    SystemPromptPart(content="Answer in english.", timestamp=timezone.now()),
                    UserPromptPart(
                        content=[
                            "What is in this image?",
                            ImageUrl(
                                url=image_url,  # not presigned URL for this conversation
                                media_type="image/png",
                                identifier="sample.png",
                            ),
                        ],
                        timestamp=timezone.now(),
                    ),
                ],
                run_id=messages[0].run_id,
            )
        ]
        yield "cannot read image."  # IRL a 400 error would be raised by the LLM

    # Use the fixture with FunctionModel
    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"cannot read image."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":50,"completionTokens":4}}\n'
    )

    # We don't check conversation messages here because the LLM would
    # normally raise an error when trying to access the image.


@freeze_time()
def test_post_conversation_with_remote_image_url(
    api_client,
    today_promt_date,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a remote URL.
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    image_url = "https://example.com/sample.png"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this image?",
        parts=[
            TextUIPart(
                text="What is in this image?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.png",
                contentType="image/png",
                url=image_url,
            )
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        assert messages == [
            ModelRequest(
                parts=[
                    SystemPromptPart(
                        content="You are a helpful test assistant :)", timestamp=timezone.now()
                    ),
                    SystemPromptPart(content=today_promt_date, timestamp=timezone.now()),
                    SystemPromptPart(content="Answer in english.", timestamp=timezone.now()),
                    UserPromptPart(
                        content=[
                            "What is in this image?",
                            ImageUrl(
                                url=image_url,  # remote URL
                                media_type="image/png",
                                identifier="sample.png",
                            ),
                        ],
                        timestamp=timezone.now(),
                    ),
                ],
                run_id=messages[0].run_id,
            )
        ]
        yield "This is an image of a single pixel."

    # Use the fixture with FunctionModel
    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"This is an image of a single pixel."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":50,"completionTokens":9}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="What is in this image?",
        reasoning=None,
        experimental_attachments=[
            Attachment(name="sample.png", contentType="image/png", url=image_url)
        ],
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="What is in this image?"),
        ],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="This is an image of a single pixel.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is an image of a single pixel."),
        ],
    )


@freeze_time("2025-10-18T20:48:20.286204Z")
def test_post_conversation_with_local_image_url_in_history(
    api_client,
    today_promt_date,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with an image URL.
    """
    chat_conversation_pk = "0be55da5-8eb7-4dad-aa0f-fea454bd5809"
    image_url = f"/media-key/{chat_conversation_pk}/sample.png"
    chat_conversation = ChatConversationFactory(
        pk=chat_conversation_pk,
        owner__language="en-us",
        messages=[
            UIMessage(
                id=str(uuid.uuid4()),
                createdAt=timezone.now(),
                content="What is in this image?",
                reasoning=None,
                experimental_attachments=[
                    Attachment(name="sample.png", contentType="image/png", url=image_url)
                ],
                role="user",
                annotations=None,
                toolInvocations=None,
                parts=[
                    TextUIPart(type="text", text="What is in this image?"),
                ],
            ),
            UIMessage(
                id=str(uuid.uuid4()),
                createdAt=timezone.now(),
                content="This is an image of a single pixel.",
                reasoning=None,
                experimental_attachments=None,
                role="assistant",
                annotations=None,
                toolInvocations=None,
                parts=[
                    TextUIPart(type="text", text="This is an image of a single pixel."),
                ],
            ),
        ],
        pydantic_messages=[
            {
                "instructions": None,
                "kind": "request",
                "parts": [
                    {
                        "content": "You are a helpful test assistant :)",
                        "dynamic_ref": None,
                        "part_kind": "system-prompt",
                        "timestamp": "2025-10-18T20:48:20.286204Z",
                    },
                    {
                        "content": today_promt_date,
                        "dynamic_ref": None,
                        "part_kind": "system-prompt",
                        "timestamp": "2025-10-18T20:48:20.286204Z",
                    },
                    {
                        "content": "Answer in english.",
                        "dynamic_ref": None,
                        "part_kind": "system-prompt",
                        "timestamp": "2025-10-18T20:48:20.286204Z",
                    },
                    {
                        "content": [
                            "What is in this image?",
                            {
                                "force_download": False,
                                "identifier": "sample.png",
                                "kind": "image-url",
                                "media_type": "image/png",
                                "url": image_url,
                                "vendor_metadata": None,
                            },
                        ],
                        "part_kind": "user-prompt",
                        "timestamp": "2025-10-18T20:48:20.286204Z",
                    },
                ],
            },
            {
                "finish_reason": None,
                "kind": "response",
                "model_name": "function::agent_model",
                "parts": [
                    {
                        "content": "This is an image of a single pixel.",
                        "id": None,
                        "part_kind": "text",
                    }
                ],
                "provider_details": None,
                "provider_name": None,
                "provider_response_id": None,
                "timestamp": "2025-10-18T20:48:20.286204Z",
                "usage": {
                    "cache_audio_read_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "details": {},
                    "input_audio_tokens": 0,
                    "input_tokens": 50,
                    "output_audio_tokens": 0,
                    "output_tokens": 9,
                },
            },
        ],
    )
    api_client.force_authenticate(user=chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"

    message = UIMessage(
        id="3",
        role="user",
        content="Give more details about this image.",
        parts=[
            TextUIPart(
                text="Give more details about this image.",
                type="text",
            ),
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        presigned_url = messages[0].parts[3].content[1].url
        assert presigned_url.startswith("http://localhost:9000/conversations-media-storage/")
        assert presigned_url.find("X-Amz-Signature=") != -1
        assert presigned_url.find("X-Amz-Date=") != -1
        assert presigned_url.find("X-Amz-Expires=") != -1

        assert messages == [
            ModelRequest(
                parts=[
                    SystemPromptPart(
                        content="You are a helpful test assistant :)",
                        timestamp=timezone.now(),
                    ),
                    SystemPromptPart(
                        content=today_promt_date,
                        timestamp=timezone.now(),
                    ),
                    SystemPromptPart(
                        content="Answer in english.",
                        timestamp=timezone.now(),
                    ),
                    UserPromptPart(
                        content=[
                            "What is in this image?",
                            ImageUrl(
                                url=presigned_url,  # presigned URL in history
                                media_type="image/png",
                                identifier="sample.png",
                            ),
                        ],
                        timestamp=timezone.now(),
                    ),
                ]
            ),
            ModelResponse(
                parts=[TextPart(content="This is an image of a single pixel.")],
                usage=RequestUsage(input_tokens=50, output_tokens=9),
                model_name="function::agent_model",
                timestamp=timezone.now(),
            ),
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=[
                            "Give more details about this image.",
                        ],
                        timestamp=timezone.now(),
                    )
                ],
                run_id=messages[2].run_id,
            ),
        ]
        yield "This is an image of square, very small and nice."

    # Use the fixture with FunctionModel
    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"This is an image of square, very small and nice."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":50,"completionTokens":11}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2 + 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="What is in this image?",
        reasoning=None,
        experimental_attachments=[
            Attachment(name="sample.png", contentType="image/png", url=image_url)
        ],
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="What is in this image?"),
        ],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="This is an image of a single pixel.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is an image of a single pixel."),
        ],
    )

    assert chat_conversation.messages[2].id == IsUUID(4)
    assert chat_conversation.messages[2] == UIMessage(
        id=chat_conversation.messages[2].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="Give more details about this image.",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="Give more details about this image."),
        ],
    )

    assert chat_conversation.messages[3].id == IsUUID(4)
    assert chat_conversation.messages[3] == UIMessage(
        id=chat_conversation.messages[3].id,  # don't test the value directly
        createdAt=timezone.now(),
        content="This is an image of square, very small and nice.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is an image of square, very small and nice."),
        ],
    )

    _run_id = chat_conversation.pydantic_messages[2]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": "You are a helpful test assistant :)",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
                {
                    "content": today_promt_date,
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
                {
                    "content": "Answer in english.",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
                {
                    "content": [
                        "What is in this image?",
                        {
                            "force_download": False,
                            "identifier": "sample.png",
                            "kind": "image-url",
                            "media_type": "image/png",
                            "url": image_url,
                            "vendor_metadata": None,
                        },
                    ],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                },
            ],
        },
        {
            "finish_reason": None,
            "kind": "response",
            "model_name": "function::agent_model",
            "parts": [
                {"content": "This is an image of a single pixel.", "id": None, "part_kind": "text"}
            ],
            "provider_details": None,
            "provider_name": None,
            "provider_response_id": None,
            "timestamp": "2025-10-18T20:48:20.286204Z",
            "usage": {
                "cache_audio_read_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "details": {},
                "input_audio_tokens": 0,
                "input_tokens": 50,
                "output_audio_tokens": 0,
                "output_tokens": 9,
            },
        },
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": ["Give more details about this image."],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                }
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": None,
            "kind": "response",
            "model_name": "function::agent_model",
            "parts": [
                {
                    "content": "This is an image of square, very small and nice.",
                    "id": None,
                    "part_kind": "text",
                }
            ],
            "provider_details": None,
            "provider_name": None,
            "provider_response_id": None,
            "timestamp": "2025-10-18T20:48:20.286204Z",
            "usage": {
                "cache_audio_read_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "details": {},
                "input_audio_tokens": 0,
                "input_tokens": 50,
                "output_audio_tokens": 0,
                "output_tokens": 11,
            },
            "run_id": _run_id,
        },
    ]
