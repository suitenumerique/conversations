"""Unit tests for chat conversation actions with audio file upload."""

from io import BytesIO
from unittest import mock

from django.contrib.sessions.backends.cache import SessionStore
from django.core.files.storage import default_storage
from django.utils import timezone

import httpx
import pytest
import responses
import respx
from dirty_equals import IsUUID
from freezegun import freeze_time
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat.ai_sdk_types import (
    Attachment,
    LanguageModelV1Source,
    SourceUIPart,
    TextUIPart,
    ToolInvocationCall,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.tests.utils import replace_uuids_with_placeholder
from chat.tools.descriptions import (
    DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT,
    DOCUMENT_SUMMARIZE_SYSTEM_PROMPT,
    SELF_DOCUMENTATION_TOOL_DESCRIPTION,
)

# enable database transactions for tests:
# transaction=True ensures that the data are available in the database
# in other threads
pytestmark = pytest.mark.django_db(transaction=True)

TRANSCRIPT_CONTENT = "Hello world from the interview."


def _expected_audio_instructions(today_prompt_date: str, audio_file_name: str) -> str:
    """Return expected concatenated system instructions for audio conversations."""
    return (
        "You are a helpful test assistant :)\n\n"
        f"{today_prompt_date}\n\n"
        "Answer in english.\n\n"
        f"{SELF_DOCUMENTATION_TOOL_DESCRIPTION}\n\n"
        f"{DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT}\n\n"
        f"{DOCUMENT_SUMMARIZE_SYSTEM_PROMPT}\n\n"
        "[Internal context] User documents are attached to this conversation. "
        "Do not request re-upload of documents; consider them already available "
        "via the internal store.\n\n"
        f"[Internal context] The following audio file(s) have been transcribed "
        f"and their transcripts are available in the document store: {audio_file_name}. "
        "Use the search tool to retrieve the transcript "
        "before answering questions about them."
    )


@pytest.fixture(autouse=True)
def mock_refresh_access_token():
    """Mock refresh_access_token to bypass token refresh in tests."""
    with mock.patch("utils.oidc.refresh_access_token") as mocked_refresh_access_token:
        session = SessionStore()
        session["oidc_access_token"] = "mocked-access-token"
        mocked_refresh_access_token.return_value = session
        yield mocked_refresh_access_token


@pytest.fixture(
    autouse=True,
    params=[
        "chat.agent_rag.document_rag_backends.find_rag_backend.FindRagBackend",
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend",
    ],
)
def ai_settings(request, settings):
    """Fixture to set AI service URLs for testing."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = request.param
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    settings.FIND_API_URL = "https://find.api.example.com"
    settings.FIND_API_KEY = "find-api-key"
    return settings


@pytest.fixture(name="mock_audio_rag_api")
def fixture_mock_audio_rag_api():
    """Fixture to mock Albert/Find API endpoints for audio transcript RAG operations.

    Unlike regular document upload, audio transcripts are stored directly without
    calling parse-beta, since they are already plain text.
    """
    search_score = 0.9
    prompt_tokens = 10
    completion_tokens = 20

    # Collection creation (Albert backend)
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "123", "name": "test-collection"},
        status=status.HTTP_200_OK,
    )

    # Direct document storage via httpx (astore_document is async) — no parse-beta needed
    respx.post("https://albert.api.etalab.gouv.fr/v1/documents").mock(
        return_value=httpx.Response(status.HTTP_201_CREATED, json={"id": 456})
    )

    # Semantic search (Albert backend)
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/search",
        json={
            "data": [
                {
                    "method": "semantic",
                    "chunk": {
                        "id": 123,
                        "content": TRANSCRIPT_CONTENT,
                        "metadata": {"document_name": "interview.ogg"},
                    },
                    "score": search_score,
                }
            ],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        },
        status=status.HTTP_200_OK,
    )

    # Document indexing (Find backend)
    responses.post(
        "https://find.api.example.com/api/v1.0/documents/index/",
        json={"id": "456", "status": "indexed"},
        status=status.HTTP_200_OK,
    )

    # Semantic search (Find backend)
    responses.post(
        "https://find.api.example.com/api/v1.0/documents/search/",
        json=[
            {
                "_source": {
                    "title.fr": "interview.ogg",
                    "content.fr": TRANSCRIPT_CONTENT,
                },
                "_score": search_score,
            }
        ],
        status=status.HTTP_200_OK,
    )


@responses.activate
@respx.mock
@freeze_time()
def test_post_conversation_with_audio_upload(
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    api_client,
    mock_audio_rag_api,  # pylint: disable=unused-argument
    today_prompt_date,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ with a ready audio file.

    The audio attachment and its linked transcript already exist in DB and S3
    (simulating a completed transcription webhook flow). Verifies:
    - has_audio=true in the document_parsing tool call
    - Transcript is stored in RAG without calling parse-beta
    - System instructions include the audio transcripts note
    - The LLM can search the transcript via document_search_rag
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    # Simulate a completed transcription: audio attachment + linked transcript attachment
    audio_attachment = ChatConversationAttachmentFactory(
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        file_name="interview.ogg",
        content_type="audio/ogg",
        upload_state=AttachmentStatus.READY,
    )
    transcript_attachment = ChatConversationAttachmentFactory(
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        key=f"{chat_conversation.pk}/attachments/interview.ogg.md",
        file_name="interview.ogg.md",
        content_type="text/markdown",
        conversion_from=audio_attachment.key,
        upload_state=AttachmentStatus.READY,
    )
    default_storage.save(transcript_attachment.key, BytesIO(TRANSCRIPT_CONTENT.encode()))

    message = UIMessage(
        id="1",
        role="user",
        content="What was discussed in the interview?",
        parts=[
            TextUIPart(
                text="What was discussed in the interview?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="interview.ogg",
                contentType="audio/ogg",
                url=f"/media-key/{audio_attachment.key}",
            )
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args='{"query": "What was discussed in the interview?"}',
                )
            }
        else:
            yield "The interview discussed Hello world."

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

    response_content = b"".join(response.streaming_content).decode("utf-8")
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '9:{"toolCallId":"XXX","toolName":"document_parsing",'
        '"args":{"documents":[{"identifier":"interview.ogg"}],"has_audio":true}}\n'
        'a:{"toolCallId":"XXX","result":{"state":"done"}}\n'
        'b:{"toolCallId":"pyd_ai_YYY","toolName":"document_search_rag"}\n'
        '9:{"toolCallId":"pyd_ai_YYY","toolName":"document_search_rag",'
        '"args":{"query":"What was discussed in the interview?"}}\n'
        'h:{"sourceType":"url","id":"<mocked_uuid>","url":"interview.ogg","title":null,'
        '"providerMetadata":{}}\n'
        'a:{"toolCallId":"pyd_ai_YYY","result":[{"url":"interview.ogg","content":'
        '"Hello world from the interview.","score":0.9}]}\n'
        '0:"The interview discussed Hello world."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":100,"completionTokens":15,'
        '"co2Impact":0.0}}\n'
    )

    # Check that the conversation was updated
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,
        createdAt=timezone.now(),
        content="What was discussed in the interview?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="What was discussed in the interview?")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,
        createdAt=timezone.now(),
        content="The interview discussed Hello world.",
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
                    args={"query": "What was discussed in the interview?"},
                    state="call",
                    step=None,
                ),
            ),
            TextUIPart(type="text", text="The interview discussed Hello world."),
            SourceUIPart(
                type="source",
                source=LanguageModelV1Source(
                    sourceType="url",
                    id=chat_conversation.messages[1].parts[2].source.id,
                    url="interview.ogg",
                    title=None,
                    providerMetadata={},
                ),
            ),
        ],
    )

    timezone_now = timezone.now().isoformat().replace("+00:00", "Z")

    assert len(chat_conversation.pydantic_messages) == 4

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]

    assert chat_conversation.pydantic_messages[0] == {
        "instructions": _expected_audio_instructions(today_prompt_date, "interview.ogg"),
        "kind": "request",
        "metadata": None,
        "parts": [
            {
                "content": ["What was discussed in the interview?"],
                "part_kind": "user-prompt",
                "timestamp": timezone_now,
            },
        ],
        "run_id": _run_id,
        "timestamp": timezone_now,
    }
    assert chat_conversation.pydantic_messages[1] == {
        "finish_reason": None,
        "kind": "response",
        "metadata": None,
        "model_name": "function::agent_model",
        "parts": [
            {
                "args": '{"query": "What was discussed in the interview?"}',
                "id": None,
                "part_kind": "tool-call",
                "tool_call_id": chat_conversation.pydantic_messages[1]["parts"][0]["tool_call_id"],
                "tool_name": "document_search_rag",
                "provider_details": None,
                "provider_name": None,
            }
        ],
        "provider_details": None,
        "provider_name": None,
        "provider_response_id": None,
        "provider_url": None,
        "timestamp": timezone_now,
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
    }
    assert chat_conversation.pydantic_messages[2] == {
        "instructions": _expected_audio_instructions(today_prompt_date, "interview.ogg"),
        "kind": "request",
        "metadata": None,
        "parts": [
            {
                "content": [
                    {
                        "content": TRANSCRIPT_CONTENT,
                        "score": 0.9,
                        "url": "interview.ogg",
                    }
                ],
                "metadata": {"sources": ["interview.ogg"]},
                "outcome": "success",
                "part_kind": "tool-return",
                "timestamp": timezone_now,
                "tool_call_id": chat_conversation.pydantic_messages[2]["parts"][0]["tool_call_id"],
                "tool_name": "document_search_rag",
            }
        ],
        "run_id": _run_id,
        "timestamp": timezone_now,
    }
    assert chat_conversation.pydantic_messages[3] == {
        "finish_reason": None,
        "kind": "response",
        "metadata": None,
        "model_name": "function::agent_model",
        "parts": [
            {
                "content": "The interview discussed Hello world.",
                "id": None,
                "part_kind": "text",
                "provider_details": None,
                "provider_name": None,
            }
        ],
        "provider_details": None,
        "provider_name": None,
        "provider_response_id": None,
        "provider_url": None,
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


@responses.activate
@freeze_time()
def test_post_conversation_with_audio_transcription_failed(
    api_client,
    mock_ai_agent_service,
):
    """
    Test POST to /api/v1/chats/{pk}/conversation/ when audio transcription has failed.

    Verifies that when the audio attachment is in TRANSCRIPTION_FAILED state, the
    document_parsing tool reports an error and the conversation is not updated.
    """
    # Albert create_collection uses requests; mock it even though storage never completes
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "123", "name": "test-collection"},
        status=status.HTTP_200_OK,
    )

    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=chat_conversation.owner)

    audio_attachment = ChatConversationAttachmentFactory(
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        file_name="interview.ogg",
        content_type="audio/ogg",
        upload_state=AttachmentStatus.TRANSCRIPTION_FAILED,
    )

    message = UIMessage(
        id="1",
        role="user",
        content="What was discussed in the interview?",
        parts=[
            TextUIPart(
                text="What was discussed in the interview?",
                type="text",
            ),
        ],
        experimental_attachments=[
            Attachment(
                name="interview.ogg",
                contentType="audio/ogg",
                url=f"/media-key/{audio_attachment.key}",
            )
        ],
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        raise RuntimeError("LLM should not be called when transcription failed")

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

    response_content = b"".join(response.streaming_content).decode("utf-8")
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '9:{"toolCallId":"XXX","toolName":"document_parsing",'
        '"args":{"documents":[{"identifier":"interview.ogg"}],"has_audio":true}}\n'
        'a:{"toolCallId":"XXX","result":{"state":"error","error":"The transcription of '
        'this audio failed. Please try again with another file."}}\n'
        'd:{"finishReason":"error","usage":{"promptTokens":0,"completionTokens":0,'
        '"co2Impact":0.0}}\n'
    )

    # Conversation should not be updated on error
    chat_conversation.refresh_from_db()
    assert len(chat_conversation.messages) == 0
