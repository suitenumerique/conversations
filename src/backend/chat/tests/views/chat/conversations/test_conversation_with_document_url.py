"""Unit tests for chat conversation actions with document URL."""

import uuid

# pylint: disable=too-many-lines
from io import BytesIO

from django.core.files.storage import default_storage
from django.utils import formats, timezone

import pytest
import responses
from dirty_equals import IsUUID
from freezegun import freeze_time
from pydantic_ai import ModelRequest, RequestUsage
from pydantic_ai.messages import (
    DocumentUrl,
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
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
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


@pytest.fixture(name="sample_document_content")
def fixture_sample_document_content():
    """Create a dummy document content as bytes."""
    # This is a simple, valid 1x1 PDF content.
    return (
        b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages"
        b"/Count 1/Kids[3 0 R]>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>"
        b"endobj\ntrailer<</Root 1 0 R>>"
    )


@responses.activate
@freeze_time()
def test_post_conversation_with_local_pdf_document_url(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    sample_document_content,
    today_promt_date,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a document URL.
    """
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": 123, "object": "collection"},
        status=200,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/parse-beta",
        json={"id": "parse_id", "object": "document content"},
        status=200,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": "document_id", "object": "document"},
        status=200,
    )

    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    file_path = f"{chat_conversation.pk}/sample.pdf"
    ChatConversationAttachmentFactory(  # Must be created by frontend
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        key=file_path,
        file_name="sample.pdf",
        content_type="application/pdf",
    )
    default_storage.save(f"{chat_conversation.pk}/sample.pdf", BytesIO(sample_document_content))
    document_url = f"/media-key/{chat_conversation.pk}/sample.pdf"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this document?",
        parts=[
            TextUIPart(
                text="What is in this document?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.pdf",
                contentType="application/pdf",
                url=document_url,
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
                    SystemPromptPart(content=today_promt_date, timestamp=timezone.now()),
                    SystemPromptPart(content="Answer in english.", timestamp=timezone.now()),
                    UserPromptPart(
                        content=[
                            "What is in this document?",
                            DocumentUrl(
                                url=presigned_url,  # presigned URL for this conversation
                                media_type="application/pdf",
                                identifier="sample.pdf",
                            ),
                        ],
                        timestamp=timezone.now(),
                    ),
                ]
            )
        ]
        yield "This is a document about a single pixel."

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
        '9:{"toolCallId":"XXX","toolName":"document_parsing",'
        '"args":{"documents":[{"identifier":"sample.pdf"}]}}\n'
        'a:{"toolCallId":"XXX","result":{"state":"done"}}\n'
        '0:"This is a document about a single pixel."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":50,"completionTokens":9}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,
        createdAt=timezone.now(),
        content="What is in this document?",
        reasoning=None,
        experimental_attachments=[
            Attachment(name="sample.pdf", contentType="application/pdf", url=document_url)
        ],
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="What is in this document?"),
        ],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,
        createdAt=timezone.now(),
        content="This is a document about a single pixel.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is a document about a single pixel."),
        ],
    )

    timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)

    assert chat_conversation.pydantic_messages == [
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": "You are a helpful test assistant :)",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": today_promt_date,
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": "Answer in english.",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": [
                        "What is in this document?",
                        {
                            "force_download": False,
                            "identifier": "sample.pdf",
                            "kind": "document-url",
                            "media_type": "application/pdf",
                            "url": document_url,
                            "vendor_metadata": None,
                        },
                    ],
                    "part_kind": "user-prompt",
                    "timestamp": timestamp,
                },
            ],
        },
        {
            "finish_reason": None,
            "kind": "response",
            "model_name": "function::agent_model",
            "parts": [
                {
                    "content": "This is a document about a single pixel.",
                    "id": None,
                    "part_kind": "text",
                }
            ],
            "provider_details": None,
            "provider_name": None,
            "provider_response_id": None,
            "timestamp": timestamp,
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
    ]


@freeze_time()
def test_post_conversation_with_local_document_wrong_url(
    api_client,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a tampered URL.
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    document_url = f"/media-key/{uuid.uuid4()}/sample.pdf"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this document?",
        parts=[
            TextUIPart(
                text="What is in this document?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.pdf",
                contentType="application/pdf",
                url=document_url,
            )
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        raise RuntimeError("LLM should not be called with tampered URL")

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
        '9:{"toolCallId":"XXX","toolName":"document_parsing",'
        '"args":{"documents":[{"identifier":"sample.pdf"}]}}\n'
        'a:{"toolCallId":"XXX",'
        '"result":{"state":"error","error":"Document '
        'URL does not belong to the conversation."}}\n'
        'd:{"finishReason":"error","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # Check that the conversation was not updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 0


@freeze_time()
def test_post_conversation_with_remote_document_url(
    api_client,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a remote URL.
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    document_url = "https://example.com/sample.pdf"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this document?",
        parts=[
            TextUIPart(
                text="What is in this document?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.pdf",
                contentType="application/pdf",
                url=document_url,
            )
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        raise RuntimeError("LLM should not be called with external URL")

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
        '9:{"toolCallId":"XXX","toolName":"document_parsing",'
        '"args":{"documents":[{"identifier":"sample.pdf"}]}}\n'
        'a:{"toolCallId":"XXX",'
        '"result":{"state":"error","error":"External document '
        'URL are not accepted yet."}}\n'
        'd:{"finishReason":"error","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # Check that the conversation was not updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 0


@freeze_time("2025-10-18T20:48:20.286204Z")
def test_post_conversation_with_local_document_url_in_history(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    today_promt_date,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a document URL.
    """
    chat_conversation_pk = "0be55da5-8eb7-4dad-aa0f-fea454bd5809"
    document_url = f"/media-key/{chat_conversation_pk}/sample.pdf"
    chat_conversation = ChatConversationFactory(
        pk=chat_conversation_pk,
        owner__language="en-us",
        messages=[
            UIMessage(
                id=str(uuid.uuid4()),
                createdAt=timezone.now(),
                content="What is in this document?",
                reasoning=None,
                experimental_attachments=[
                    Attachment(name="sample.pdf", contentType="application/pdf", url=document_url)
                ],
                role="user",
                annotations=None,
                toolInvocations=None,
                parts=[
                    TextUIPart(type="text", text="What is in this document?"),
                ],
            ),
            UIMessage(
                id=str(uuid.uuid4()),
                createdAt=timezone.now(),
                content="This is a document about a single pixel.",
                reasoning=None,
                experimental_attachments=None,
                role="assistant",
                annotations=None,
                toolInvocations=None,
                parts=[
                    TextUIPart(type="text", text="This is a document about a single pixel."),
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
                            "What is in this document?",
                            {
                                "force_download": False,
                                "identifier": "sample.pdf",
                                "kind": "document-url",
                                "media_type": "application/pdf",
                                "url": document_url,
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
                        "content": "This is a document about a single pixel.",
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

    document_url = f"/media-key/{chat_conversation.pk}/sample.pdf"

    message = UIMessage(
        id="3",
        role="user",
        content="Give more details about this document.",
        parts=[
            TextUIPart(
                text="Give more details about this document.",
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
                            "What is in this document?",
                            DocumentUrl(
                                url=presigned_url,  # presigned URL in history
                                media_type="application/pdf",
                                identifier="sample.pdf",
                            ),
                        ],
                        timestamp=timezone.now(),
                    ),
                ]
            ),
            ModelResponse(
                parts=[TextPart(content="This is a document about a single pixel.")],
                usage=RequestUsage(input_tokens=50, output_tokens=9),
                model_name="function::agent_model",
                timestamp=timezone.now(),
            ),
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=[
                            "Give more details about this document.",
                        ],
                        timestamp=timezone.now(),
                    )
                ]
            ),
        ]
        yield "This is a document of square, very small and nice."

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
        '0:"This is a document of square, very small and nice."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":50,"completionTokens":11}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2 + 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,
        createdAt=timezone.now(),
        content="What is in this document?",
        reasoning=None,
        experimental_attachments=[
            Attachment(name="sample.pdf", contentType="application/pdf", url=document_url)
        ],
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="What is in this document?"),
        ],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,
        createdAt=timezone.now(),
        content="This is a document about a single pixel.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is a document about a single pixel."),
        ],
    )

    assert chat_conversation.messages[2].id == IsUUID(4)
    assert chat_conversation.messages[2] == UIMessage(
        id=chat_conversation.messages[2].id,
        createdAt=timezone.now(),
        content="Give more details about this document.",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="Give more details about this document."),
        ],
    )

    assert chat_conversation.messages[3].id == IsUUID(4)
    assert chat_conversation.messages[3] == UIMessage(
        id=chat_conversation.messages[3].id,
        createdAt=timezone.now(),
        content="This is a document of square, very small and nice.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is a document of square, very small and nice."),
        ],
    )

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
                        "What is in this document?",
                        {
                            "force_download": False,
                            "identifier": "sample.pdf",
                            "kind": "document-url",
                            "media_type": "application/pdf",
                            "url": document_url,
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
                    "content": "This is a document about a single pixel.",
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
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": ["Give more details about this document."],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-10-18T20:48:20.286204Z",
                }
            ],
        },
        {
            "finish_reason": None,
            "kind": "response",
            "model_name": "function::agent_model",
            "parts": [
                {
                    "content": "This is a document of square, very small and nice.",
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
        },
    ]


@responses.activate
@freeze_time()
@pytest.mark.parametrize(
    "file_name,content_type",
    [
        ("sample.txt", "text/plain"),
        ("image.md", "text/markdown"),
        ("data.csv", "text/csv"),
    ],
)
def test_post_conversation_with_local_not_pdf_document_url(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    today_promt_date,
    mock_ai_agent_service,
    file_name,
    content_type,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a document URL.
    """
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": 123, "object": "collection"},
        status=200,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/parse-beta",
        json={"id": "parse_id", "object": "document content"},
        status=200,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": "document_id", "object": "document"},
        status=200,
    )

    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    file_path = f"{chat_conversation.pk}/sample.pdf"
    ChatConversationAttachmentFactory(  # Must be created by frontend
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        key=file_path,
        file_name=file_name,
        content_type=content_type,
    )
    default_storage.save(f"{chat_conversation.pk}/{file_name}", BytesIO(b"Just some text content."))
    document_url = f"/media-key/{chat_conversation.pk}/{file_name}"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this document?",
        parts=[
            TextUIPart(
                text="What is in this document?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name=file_name,
                contentType=content_type,
                url=document_url,
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
                    SystemPromptPart(
                        content=(
                            "If the user wants specific information from a document, "
                            "invoke web_search_albert_rag with an appropriate query string."
                            "Do not ask the user for the document; rely on the tool to locate "
                            "and return relevant passages."
                        ),
                        timestamp=timezone.now(),
                    ),
                    SystemPromptPart(
                        content=(
                            "When you receive a result from the summarization tool, you MUST "
                            "return it directly to the user without any modification, "
                            "paraphrasing, or additional summarization."
                            "The tool already produces optimized summaries that should "
                            "be presented verbatim."
                            "You may translate the summary if required, but you MUST preserve "
                            "all the information from the original summary."
                            "You may add a follow-up question after the summary if needed."
                        ),
                        timestamp=timezone.now(),
                    ),
                    UserPromptPart(
                        content=[
                            "What is in this document?",
                            # No presigned URL for non-PDF documents (not supporter by LLM)
                        ],
                        timestamp=timezone.now(),
                    ),
                ]
            )
        ]
        yield "This is a document about you."

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
        '9:{"toolCallId":"XXX","toolName":"document_parsing",'
        f'"args":{{"documents":[{{"identifier":"{file_name}"}}]}}}}\n'
        'a:{"toolCallId":"XXX","result":{"state":"done"}}\n'
        '0:"This is a document about you."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":50,"completionTokens":7}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,
        createdAt=timezone.now(),
        content="What is in this document?",
        reasoning=None,
        experimental_attachments=None,  # We should fix this, but for now document appears in source
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="What is in this document?"),
        ],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,
        createdAt=timezone.now(),
        content="This is a document about you.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="This is a document about you."),
        ],
    )

    timestamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)

    assert chat_conversation.pydantic_messages == [
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": "You are a helpful test assistant :)",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": today_promt_date,
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": "Answer in english.",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": "If the user wants specific information from a "
                    "document, invoke web_search_albert_rag with an "
                    "appropriate query string.Do not ask the user for the "
                    "document; rely on the tool to locate and return "
                    "relevant passages.",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": "When you receive a result from the summarization "
                    "tool, you MUST return it directly to the user without "
                    "any modification, paraphrasing, or additional "
                    "summarization.The tool already produces optimized "
                    "summaries that should be presented verbatim.You may "
                    "translate the summary if required, but you MUST "
                    "preserve all the information from the original "
                    "summary.You may add a follow-up question after the "
                    "summary if needed.",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": timestamp,
                },
                {
                    "content": [
                        "What is in this document?",
                    ],
                    "part_kind": "user-prompt",
                    "timestamp": timestamp,
                },
            ],
        },
        {
            "finish_reason": None,
            "kind": "response",
            "model_name": "function::agent_model",
            "parts": [
                {
                    "content": "This is a document about you.",
                    "id": None,
                    "part_kind": "text",
                }
            ],
            "provider_details": None,
            "provider_name": None,
            "provider_response_id": None,
            "timestamp": timestamp,
            "usage": {
                "cache_audio_read_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "details": {},
                "input_audio_tokens": 0,
                "input_tokens": 50,
                "output_audio_tokens": 0,
                "output_tokens": 7,
            },
        },
    ]
