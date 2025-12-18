"""Unit tests for chat conversation actions with document search RAG functionality."""

# pylint: disable=too-many-lines
import base64
import dataclasses
import json
import logging
from io import BytesIO
from unittest import mock
from unittest.mock import Mock

from django.utils import formats, timezone

import httpx
import pytest
import responses
import respx
from dirty_equals import IsUUID
from freezegun import freeze_time
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from rest_framework import status

from core.feature_flags.flags import FeatureToggle

from chat.agents.summarize import SummarizationAgent
from chat.ai_sdk_types import (
    Attachment,
    LanguageModelV1Source,
    SourceUIPart,
    TextUIPart,
    ToolInvocationCall,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.factories import ChatConversationFactory
from chat.tests.utils import replace_uuids_with_placeholder

# enable database transactions for tests:
# transaction=True ensures that the data are available in the database
# in other threads
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(
    autouse=True,
    params=[
        "chat.agent_rag.document_rag_backends.find_rag_backend.FindRagBackend",
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend",
    ],
)
def ai_settings(request, settings):
    """Fixture to set AI service URLs for testing."""

    # enable on rag document search tool
    settings.RAG_DOCUMENT_SEARCH_BACKEND = request.param
    settings.RAG_WEB_SEARCH_PROMPT_UPDATE = (
        "Based on the following document contents:\n\n{search_results}\n\n"
        "Please answer the user's question: {user_prompt}"
    )

    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"

    # Albert API settings
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"

    # Find API settings
    settings.FIND_API_URL = "https://find.api.example.com"
    settings.FIND_API_KEY = "find-api-key"

    return settings


@pytest.fixture(autouse=True)
def mock_process_request():
    """Mock process_request to bypass authentication in tests."""
    with mock.patch(
        "lasuite.oidc_login.decorators.RefreshOIDCAccessToken.process_request"
    ) as mocked_process_request:
        mocked_process_request.return_value = None
        yield mocked_process_request


@pytest.fixture(autouse=True)
def mock_refresh_access_token():
    """Mock refresh_access_token to bypass token refresh in tests."""
    with mock.patch("utils.oidc.refresh_access_token") as mocked_refresh_access_token:
        mocked_refresh_access_token.return_value = Mock(spec=httpx.Client)
        yield mocked_refresh_access_token


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


@pytest.fixture(name="mock_document_api")
def fixture_mock_document_api():
    """Fixture to mock the Albert API endpoints."""
    # Mock collection creation

    document_name = "sample.pdf"
    document_content = "This is the content of the PDF."
    prompt_tokens = 10
    completion_tokens = 20
    search_method = "semantic"
    search_score = 0.9

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
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
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
                    "method": search_method,
                    "chunk": {
                        "id": 123,
                        "content": document_content,
                        "metadata": {"document_name": document_name},
                    },
                    "score": search_score,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        },
        status=status.HTTP_200_OK,
    )

    # Mock document indexing (Find API)
    responses.post(
        "https://find.api.example.com/api/v1.0/documents/index/",
        json={"id": "456", "status": "indexed"},
        status=status.HTTP_200_OK,
    )

    # Mock document search (Find API)
    responses.post(
        "https://find.api.example.com/api/v1.0/documents/search/",
        json=[
            {
                "_source": {
                    "title.fr": document_name,
                    "content.fr": document_content,
                },
                "_score": search_score,
            }
        ],
        status=status.HTTP_200_OK,
    )


@pytest.fixture(name="mock_summarization_agent")
def fixture_mock_summarization_agent():
    """Mock the SummarizationAgent to return a fixed summary."""

    def summarization_model(_messages: list[ModelMessage], _info: AgentInfo):
        """Mock summarization model function."""
        return ModelResponse(parts=[TextPart(content="The document discusses various topics.")])

    @dataclasses.dataclass(init=False)
    class SummarizationAgentMock(SummarizationAgent):
        """Mocked SummarizationAgent using a FunctionModel."""

        def __init__(self, **kwargs):
            """Override the model with a FunctionModel."""
            super().__init__(**kwargs)
            self._model = FunctionModel(function=summarization_model)  # pylint: disable=protected-access

    with mock.patch("chat.tools.document_summarize.SummarizationAgent", new=SummarizationAgentMock):
        yield


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


@responses.activate
@respx.mock
@freeze_time()
def test_post_conversation_with_document_upload(
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    mock_document_api,  # pylint: disable=unused-argument
    sample_pdf_content,
    today_promt_date,
    mock_ai_agent_service,
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

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args='{"query": "What does the document say?"}',
                )
            }
        else:
            yield "From the document, I can see that it says 'Hello PDF'."

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
        'b:{"toolCallId":"pyd_ai_YYY","toolName":"document_search_rag"}\n'
        '9:{"toolCallId":"pyd_ai_YYY","toolName":"document_search_rag",'
        '"args":{"query":"What does the document say?"}}\n'
        'h:{"sourceType":"url","id":"<mocked_uuid>","url":"sample.pdf","title":null,'
        '"providerMetadata":{}}\n'
        'a:{"toolCallId":"pyd_ai_YYY","result":[{"url":"sample.pdf","content":"This '
        'is the content of the PDF.","score":0.9}]}\n'
        "0:\"From the document, I can see that it says 'Hello PDF'.\"\n"
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":100,"completionTokens":20}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,
        createdAt=timezone.now(),
        content="What does the document say?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="What does the document say?")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,
        createdAt=timezone.now(),
        content="From the document, I can see that it says 'Hello PDF'.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    toolCallId=chat_conversation.messages[1].parts[0].toolInvocation.toolCallId,
                    toolName="document_search_rag",
                    args={"query": "What does the document say?"},
                    state="call",
                    step=None,
                ),
            ),
            TextUIPart(type="text", text="From the document, I can see that it says 'Hello PDF'."),
            SourceUIPart(
                type="source",
                source=LanguageModelV1Source(
                    sourceType="url",
                    id=chat_conversation.messages[1].parts[2].source.id,
                    url="sample.pdf",
                    title=None,
                    providerMetadata={},
                ),
            ),
        ],
    )

    timezone_now = timezone.now().isoformat().replace("+00:00", "Z")
    _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)

    assert len(chat_conversation.pydantic_messages) == 4

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]

    assert chat_conversation.pydantic_messages[0] == {
        "instructions": "You are a helpful test assistant :)\n\n"
        f"{today_promt_date}\n\n"
        "Answer in english.\n\n"
        "Use document_search_rag ONLY to retrieve specific passages from "
        "attached documents. Do NOT use it to summarize; for summaries, "
        "call the summarize tool instead.\n\nWhen you receive a result from the "
        "summarization tool, you MUST return it directly to the user without "
        "any modification, paraphrasing, or additional summarization."
        "The tool already produces optimized summaries that should be "
        "presented verbatim.You may translate the summary if required, "
        "but you MUST preserve all the information from the original summary."
        "You may add a follow-up question after the summary if needed.\n\n"
        "[Internal context] User documents are attached to this conversation. "
        "Do not request re-upload of documents; consider them already "
        "available via the internal store.",
        "kind": "request",
        "parts": [
            {
                "content": ["What does the document say?"],
                "part_kind": "user-prompt",
                "timestamp": timezone_now,
            },
        ],
        "run_id": _run_id,
    }
    assert chat_conversation.pydantic_messages[1] == {
        "finish_reason": None,
        "kind": "response",
        "model_name": "function::agent_model",
        "parts": [
            {
                "args": '{"query": "What does the document say?"}',
                "id": None,
                "part_kind": "tool-call",
                "tool_call_id": chat_conversation.pydantic_messages[1]["parts"][0]["tool_call_id"],
                "tool_name": "document_search_rag",
            }
        ],
        "provider_details": None,
        "provider_name": None,
        "provider_response_id": None,
        "timestamp": timezone_now,
        "usage": {
            "cache_audio_read_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
            "input_audio_tokens": 0,
            "input_tokens": 50,
            "output_audio_tokens": 0,
            "output_tokens": 8,
        },
        "run_id": _run_id,
    }
    assert chat_conversation.pydantic_messages[2] == {
        "instructions": (
            "You are a helpful test assistant :)\n\n"
            f"{today_promt_date}\n\n"
            "Answer in english.\n\n"
            "Use document_search_rag ONLY to retrieve specific passages from "
            "attached documents. Do NOT use it to summarize; for summaries, "
            "call the summarize tool instead.\n\nWhen you receive a result from the "
            "summarization tool, you MUST return it directly to the user without "
            "any modification, paraphrasing, or additional summarization."
            "The tool already produces optimized summaries that should be "
            "presented verbatim.You may translate the summary if required, "
            "but you MUST preserve all the information from the original summary."
            "You may add a follow-up question after the summary if needed.\n\n"
            "[Internal context] User documents are attached to this conversation. "
            "Do not request re-upload of documents; consider them already "
            "available via the internal store."
        ),
        "kind": "request",
        "parts": [
            {
                "content": [
                    {
                        "content": "This is the content of the PDF.",
                        "score": 0.9,
                        "url": "sample.pdf",
                    }
                ],
                "metadata": {"sources": ["sample.pdf"]},
                "part_kind": "tool-return",
                "timestamp": timezone_now,
                "tool_call_id": chat_conversation.pydantic_messages[2]["parts"][0]["tool_call_id"],
                "tool_name": "document_search_rag",
            }
        ],
        "run_id": _run_id,
    }
    assert chat_conversation.pydantic_messages[3] == {
        "finish_reason": None,
        "kind": "response",
        "model_name": "function::agent_model",
        "parts": [
            {
                "content": "From the document, I can see that it says 'Hello PDF'.",
                "id": None,
                "part_kind": "text",
            }
        ],
        "provider_details": None,
        "provider_name": None,
        "provider_response_id": None,
        "timestamp": timezone_now,
        "usage": {
            "cache_audio_read_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
            "input_audio_tokens": 0,
            "input_tokens": 50,
            "output_audio_tokens": 0,
            "output_tokens": 12,
        },
        "run_id": _run_id,
    }


@responses.activate
@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_with_document_upload_feature_disabled(
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    caplog,
    mock_openai_stream,  # pylint: disable=unused-argument
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

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)
    assert response_content == (
        '0:"From the document, I can see that "\n'
        "0:\"it says 'Hello PDF'.\"\n"
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":150,"completionTokens":25}}\n'
    )
    # This behavior must be improved in the future to inform the user properly
    assert "Document upload feature is disabled, ignoring input documents." in caplog.text


@responses.activate
@respx.mock
@freeze_time()
def test_post_conversation_with_document_upload_summarize(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # noqa: PLR0913
    api_client,
    mock_document_api,  # pylint: disable=unused-argument
    sample_pdf_content,
    today_promt_date,
    mock_ai_agent_service,
    mock_summarization_agent,  # pylint: disable=unused-argument
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
        content="Make a summary of this document.",
        parts=[
            TextUIPart(
                text="Make a summary of this document.",
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

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="summarize",
                    json_args="{}",
                )
            }
        else:
            yield "The document discusses various topics."

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
        'b:{"toolCallId":"pyd_ai_YYY","toolName":"summarize"}\n'
        '9:{"toolCallId":"pyd_ai_YYY","toolName":"summarize","args":{}}\n'
        'h:{"sourceType":"url","id":"<mocked_uuid>","url":"sample.pdf.md",'
        '"title":null,"providerMetadata":{}}\n'
        'a:{"toolCallId":"pyd_ai_YYY","result":"The '
        'document discusses various topics."}\n'
        '0:"The document discusses various topics."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":287,"completionTokens":19}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,
        createdAt=timezone.now(),
        content="Make a summary of this document.",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Make a summary of this document.")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,
        createdAt=timezone.now(),
        content="The document discusses various topics.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    toolCallId=chat_conversation.messages[1].parts[0].toolInvocation.toolCallId,
                    toolName="summarize",
                    args={},
                    state="call",
                    step=None,
                ),
            ),
            TextUIPart(type="text", text="The document discusses various topics."),
            SourceUIPart(
                type="source",
                source=LanguageModelV1Source(
                    sourceType="url",
                    id=chat_conversation.messages[1].parts[2].source.id,
                    url="sample.pdf.md",  # might be fixed in the future
                    title=None,
                    providerMetadata={},
                ),
            ),
        ],
    )

    timezone_now = timezone.now().isoformat().replace("+00:00", "Z")
    _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)

    assert len(chat_conversation.pydantic_messages) == 4

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages[0] == {
        "instructions": (
            "You are a helpful test assistant :)\n\n"
            f"{today_promt_date}\n\n"
            "Answer in english.\n\n"
            "Use document_search_rag ONLY to retrieve specific passages from "
            "attached documents. Do NOT use it to summarize; for summaries, "
            "call the summarize tool instead.\n\nWhen you receive a result from the "
            "summarization tool, you MUST return it directly to the user without "
            "any modification, paraphrasing, or additional summarization."
            "The tool already produces optimized summaries that should be "
            "presented verbatim.You may translate the summary if required, "
            "but you MUST preserve all the information from the original summary."
            "You may add a follow-up question after the summary if needed.\n\n"
            "[Internal context] User documents are attached to this conversation. "
            "Do not request re-upload of documents; consider them already "
            "available via the internal store."
        ),
        "kind": "request",
        "parts": [
            {
                "content": ["Make a summary of this document."],
                "part_kind": "user-prompt",
                "timestamp": timezone_now,
            },
        ],
        "run_id": _run_id,
    }
    assert chat_conversation.pydantic_messages[1] == {
        "finish_reason": None,
        "kind": "response",
        "model_name": "function::agent_model",
        "parts": [
            {
                "args": "{}",
                "id": None,
                "part_kind": "tool-call",
                "tool_call_id": chat_conversation.pydantic_messages[1]["parts"][0]["tool_call_id"],
                "tool_name": "summarize",
            }
        ],
        "provider_details": None,
        "provider_name": None,
        "provider_response_id": None,
        "timestamp": timezone_now,
        "usage": {
            "cache_audio_read_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
            "input_audio_tokens": 0,
            "input_tokens": 50,
            "output_audio_tokens": 0,
            "output_tokens": 1,
        },
        "run_id": _run_id,
    }
    assert chat_conversation.pydantic_messages[2] == {
        "instructions": (
            "You are a helpful test assistant :)\n\n"
            f"{today_promt_date}\n\n"
            "Answer in english.\n\n"
            "Use document_search_rag ONLY to retrieve specific passages from "
            "attached documents. Do NOT use it to summarize; for summaries, "
            "call the summarize tool instead.\n\nWhen you receive a result from the "
            "summarization tool, you MUST return it directly to the user without "
            "any modification, paraphrasing, or additional summarization."
            "The tool already produces optimized summaries that should be "
            "presented verbatim.You may translate the summary if required, "
            "but you MUST preserve all the information from the original summary."
            "You may add a follow-up question after the summary if needed.\n\n"
            "[Internal context] User documents are attached to this conversation. "
            "Do not request re-upload of documents; consider them already "
            "available via the internal store."
        ),
        "kind": "request",
        "parts": [
            {
                "content": "The document discusses various topics.",
                "metadata": {"sources": ["sample.pdf.md"]},
                "part_kind": "tool-return",
                "timestamp": timezone_now,
                "tool_call_id": chat_conversation.pydantic_messages[2]["parts"][0]["tool_call_id"],
                "tool_name": "summarize",
            }
        ],
        "run_id": _run_id,
    }
    assert chat_conversation.pydantic_messages[3] == {
        "finish_reason": None,
        "kind": "response",
        "model_name": "function::agent_model",
        "parts": [
            {"content": "The document discusses various topics.", "id": None, "part_kind": "text"}
        ],
        "provider_details": None,
        "provider_name": None,
        "provider_response_id": None,
        "timestamp": timezone_now,
        "usage": {
            "cache_audio_read_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
            "input_audio_tokens": 0,
            "input_tokens": 50,
            "output_audio_tokens": 0,
            "output_tokens": 6,
        },
        "run_id": _run_id,
    }
