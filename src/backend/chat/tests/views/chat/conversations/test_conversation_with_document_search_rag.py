"""Unit tests for chat conversation actions with document search RAG functionality."""

# pylint: disable=too-many-lines
import base64
import json
import logging
from io import BytesIO

from django.utils import timezone

import httpx
import pytest
import responses
import respx
from freezegun import freeze_time
from rest_framework import status

from core.feature_flags.flags import FeatureToggle

from chat.ai_sdk_types import (
    Attachment,
    LanguageModelV1Source,
    SourceUIPart,
    TextUIPart,
    UIMessage,
)
from chat.factories import ChatConversationFactory

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

    # Enable Albert API for document search
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_search.albert_api.AlbertRagDocumentSearch"
    )
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    settings.RAG_WEB_SEARCH_PROMPT_UPDATE = (
        "Based on the following document contents:\n\n{search_results}\n\n"
        "Please answer the user's question: {user_prompt}"
    )

    # Set up AI routing model settings for intent detection
    settings.AI_ROUTING_MODEL = "mini-model"
    settings.AI_ROUTING_MODEL_BASE_URL = "https://www.mini-ai-service.com/"
    settings.AI_ROUTING_MODEL_API_KEY = "test-routing-api-key"
    settings.AI_ROUTING_SYSTEM_PROMPT = (
        "You are an intent detection model. "
        "Return attachment_summary as true if the user wants to talk about the document."
    )

    return settings


@pytest.fixture(name="sample_pdf_content")
def fixture_sample_pdf_content():
    """Create a dummy PDF content as BytesIO."""
    # This is a simple, valid one-page PDF content.
    pdf_data = (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources <<>> >>\nendobj\n"
        b"4 0 obj\n<< /Length 35 >>\nstream\nBT /F1 24 Tf 100 700 Td (Hello PDF) "
        b"Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000062 00000 n \n"
        b"0000000118 00000 n \n0000000210 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n288\n%%EOF"
    )
    return BytesIO(pdf_data)


@pytest.fixture(name="mock_albert_api")
def fixture_mock_albert_api():
    """Fixture to mock the Albert API endpoints."""
    # Mock collection creation
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "123", "name": "test-collection"},
        status=status.HTTP_200_OK,
    )

    # Mock PDF parsing
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/parse-beta",
        json={
            "data": [
                {
                    "content": "This is the content of the PDF.",
                    "metadata": {"document_name": "sample.pdf"},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        },
        status=status.HTTP_200_OK,
    )

    # Mock document upload
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 456},
        status=status.HTTP_201_CREATED,
    )

    # Mock document search
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/search",
        json={
            "data": [
                {
                    "method": "semantic",
                    "chunk": {
                        "id": 123,
                        "content": "This is the content of the PDF.",
                        "metadata": {"document_name": "sample.pdf"},
                    },
                    "score": 0.9,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        },
        status=status.HTTP_200_OK,
    )


@pytest.fixture(name="mock_openai_stream")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_openai_stream():
    """
    Fixture to mock the OpenAI stream response for document search queries.
    """
    openai_stream = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {"content": "From the document, I can see that "},
                        "index": 0,
                        "finish_reason": None,
                    }
                ],
                "object": "chat.completion.chunk",
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {"content": "it says 'Hello PDF'."},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "object": "chat.completion.chunk",
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 25,
                    "total_tokens": 175,
                },
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    async def mock_stream():
        for line in openai_stream.splitlines(keepends=True):
            yield line.encode()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, stream=mock_stream())
    )

    return route


@pytest.fixture(name="mock_intent_detection_document")
def fixture_mock_intent_detection_document():
    """Fixture to mock the intent detection response for document summary."""
    intent_response = {
        "id": "chatcmpl-intent-123",
        "object": "chat.completion",
        "created": int(timezone.make_naive(timezone.now()).timestamp()),
        "model": "mini-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"web_search": false, "attachment_summary": false}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
    }

    route = respx.post("https://www.mini-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, json=intent_response)
    )

    return route


@pytest.fixture(name="mock_intent_detection_document_summarize")
def fixture_mock_intent_detection_document_summarize():
    """Fixture to mock the intent detection response for document summary."""
    intent_response = {
        "id": "chatcmpl-intent-123",
        "object": "chat.completion",
        "created": int(timezone.make_naive(timezone.now()).timestamp()),
        "model": "mini-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"web_search": false, "attachment_summary": true}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
    }

    route = respx.post("https://www.mini-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, json=intent_response)
    )

    return route


@responses.activate
@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_with_document_upload_summarize(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    mock_albert_api,  # pylint: disable=unused-argument
    mock_openai_stream,  # pylint: disable=unused-argument
    mock_intent_detection_document_summarize,  # pylint: disable=unused-argument
    sample_pdf_content,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a PDF document
    when user wants a summary of the document.
    """
    chat_conversation = ChatConversationFactory()
    api_client.force_authenticate(user=chat_conversation.owner)

    pdf_base64 = base64.b64encode(sample_pdf_content.read()).decode("utf-8")
    message = UIMessage(
        id="1",
        role="user",
        content="What does the document say?",
        parts=[
            TextUIPart(
                text="What does the document say?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.pdf",
                contentType="application/pdf",
                url=f"data:application/pdf;base64,{pdf_base64}",
            )
        ],
    )

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
    assert response_content == '3:"attachment_summary_not_supported"\n'

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 0  # might be improved in the future
    assert len(chat_conversation.pydantic_messages) == 0  # might be improved in the future


@responses.activate
@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_with_document_upload(  # noqa:PLR0913  # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    mock_albert_api,  # pylint: disable=unused-argument
    mock_openai_stream,  # pylint: disable=unused-argument
    mock_intent_detection_document,  # pylint: disable=unused-argument
    sample_pdf_content,
    mock_uuid4,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a PDF document.
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    pdf_base64 = base64.b64encode(sample_pdf_content.read()).decode("utf-8")
    message = UIMessage(
        id="1",
        role="user",
        content="What does the document say?",
        parts=[
            TextUIPart(
                text="What does the document say?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.pdf",
                contentType="application/pdf",
                url=f"data:application/pdf;base64,{pdf_base64}",
            )
        ],
    )

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
    assert response_content == (
        f'9:{{"toolCallId":"{mock_uuid4}","toolName":'
        '"document_parsing","args":{"documents":[{"identifier":"sample.pdf"}]}}\n'
        f'a:{{"toolCallId":"{mock_uuid4}","result":{{"state":"done"}}}}\n'
        f'h:{{"sourceType":"url","id":"{mock_uuid4}",'
        '"url":"sample.pdf","title":null,"providerMetadata":{}}\n'
        '0:"From the document, I can see that "\n'
        "0:\"it says 'Hello PDF'.\"\n"
        'd:{"finishReason":"stop","usage":{"promptTokens":150,"completionTokens":25}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2
    assert chat_conversation.messages[0] == UIMessage(
        id=str(mock_uuid4),
        createdAt=timezone.now(),
        content="What does the document say?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="What does the document say?")],
    )
    assert chat_conversation.messages[1] == UIMessage(
        id=str(mock_uuid4),
        createdAt=timezone.now(),
        content="From the document, I can see that it says 'Hello PDF'.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(type="text", text="From the document, I can see that it says 'Hello PDF'."),
            SourceUIPart(
                type="source",
                source=LanguageModelV1Source(
                    sourceType="url",
                    id=str(mock_uuid4),
                    url="sample.pdf",
                    title=None,
                    providerMetadata={},
                ),
            ),
        ],
    )

    assert len(chat_conversation.pydantic_messages) == 2
    assert chat_conversation.pydantic_messages[0] == {
        "instructions": None,
        "kind": "request",
        "parts": [
            {
                "content": "You are a helpful assistant. Escape formulas or any "
                "math notation between `$$`, like `$$x^2 + y^2 = z^2$$` "
                "or `$$C_l$$`. You can use Markdown to format your "
                "answers. ",
                "dynamic_ref": None,
                "part_kind": "system-prompt",
                "timestamp": "2025-07-25T10:36:35.297675Z",
            },
            {
                "content": "Today is Friday 25/07/2025.",
                "dynamic_ref": None,
                "part_kind": "system-prompt",
                "timestamp": "2025-07-25T10:36:35.297675Z",
            },
            {
                "content": "Answer in english.",
                "dynamic_ref": None,
                "part_kind": "system-prompt",
                "timestamp": "2025-07-25T10:36:35.297675Z",
            },
            {
                "content": [
                    "Based on the following document contents:\n"
                    "\n"
                    " - From: sample.pdf:\n"
                    "   content: This is the content of the PDF.\n"
                    "\n"
                    "\n"
                    "\n"
                    "\n"
                    "\n"
                    "Please answer the user's question: What does the "
                    "document say?"
                ],
                "part_kind": "user-prompt",
                "timestamp": "2025-07-25T10:36:35.297675Z",
            },
        ],
    }
    assert chat_conversation.pydantic_messages[1] == {
        "finish_reason": "stop",
        "kind": "response",
        "model_name": "test-model",
        "parts": [
            {
                "content": "From the document, I can see that it says 'Hello PDF'.",
                "id": None,
                "part_kind": "text",
            }
        ],
        "provider_details": {"finish_reason": "stop"},
        "provider_name": "openai",
        "provider_response_id": "chatcmpl-1234567890",
        "timestamp": "2025-07-25T10:36:35.297675Z",
        "usage": {
            "cache_audio_read_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
            "input_audio_tokens": 0,
            "input_tokens": 150,
            "output_audio_tokens": 0,
            "output_tokens": 25,
        },
    }


@responses.activate
@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_with_document_upload_feature_disabled(  # noqa:PLR0913  # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    caplog,
    mock_albert_api,  # pylint: disable=unused-argument
    mock_openai_stream,  # pylint: disable=unused-argument
    mock_intent_detection_document,  # pylint: disable=unused-argument
    sample_pdf_content,
    feature_flags,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a PDF document while feature is disabled.
    """
    feature_flags.web_search = FeatureToggle.DISABLED
    feature_flags.document_upload = FeatureToggle.DISABLED
    caplog.set_level(logging.WARNING)

    chat_conversation = ChatConversationFactory()
    api_client.force_authenticate(user=chat_conversation.owner)

    pdf_base64 = base64.b64encode(sample_pdf_content.read()).decode("utf-8")
    message = UIMessage(
        id="1",
        role="user",
        content="What does the document say?",
        parts=[
            TextUIPart(
                text="What does the document say?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="sample.pdf",
                contentType="application/pdf",
                url=f"data:application/pdf;base64,{pdf_base64}",
            )
        ],
    )

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
    assert response_content == (
        '0:"From the document, I can see that "\n'
        "0:\"it says 'Hello PDF'.\"\n"
        'd:{"finishReason":"stop","usage":{"promptTokens":150,"completionTokens":25}}\n'
    )

    # This behavior must be improved in the future to inform the user properly
    assert "Document upload feature is disabled, ignoring input documents." in caplog.text
