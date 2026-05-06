"""End-to-end conversation tests for project-level RAG files.

These tests cover the full request path for a conversation that belongs to a
project carrying indexed RAG files. They exercise:
- the `_check_should_enable_rag` gate (registers the RAG tool)
- the search tool's wiring of `read_only_collection_id` (project collection)
- the conversation-streaming response path
"""

import json
from unittest import mock

from django.contrib.sessions.backends.cache import SessionStore

import pytest
import respx
from freezegun import freeze_time
from httpx import Response
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat.constants import ACCESS_FULL_CONTEXT
from chat.factories import (
    ChatConversationAttachmentFactory,
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
)
from chat.llm_configuration import LLModel, LLMProvider

# transaction=True: same setup as test_conversation_with_document_upload.py
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Albert backend + LLM settings, mirroring the document_upload test fixture."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.RAG_DOCUMENT_PARSER = "chat.agent_rag.document_converter.parser.AlbertParser"
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


@pytest.fixture(name="mock_refresh_access_token", autouse=True)
def mock_refresh_access_token_fixture():
    """Bypass OIDC token refresh (same pattern as the document_upload tests)."""

    with mock.patch("utils.oidc.refresh_access_token") as mocked:
        session = SessionStore()
        session["oidc_access_token"] = "mocked-access-token"
        mocked.return_value = session
        yield mocked


ASK_DOC_MESSAGE = {
    "id": "msg-1",
    "role": "user",
    "parts": [{"text": "What does the project doc say?", "type": "text"}],
    "content": "What does the project doc say?",
    "createdAt": "2025-07-03T15:22:17.105Z",
}


def _mock_albert_search(content="The project doc says hello.", document_name="project-doc.txt"):
    """The search tool now uses async httpx (asearch); mock with respx, not responses."""
    return respx.post("https://albert.api.etalab.gouv.fr/v1/search").mock(
        return_value=Response(
            status.HTTP_200_OK,
            json={
                "data": [
                    {
                        "method": "semantic",
                        "chunk": {
                            "id": 1,
                            "content": content,
                            "metadata": {"document_name": document_name},
                        },
                        "score": 0.9,
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )
    )


@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_searches_project_collection(
    api_client,
    mock_ai_agent_service,
):
    """The agent's RAG search hits the project collection when no conversation collection exists.

    Setup mirrors the live failure: project has an indexed file (collection_id set),
    conversation in that project has no own attachments. Without the project wiring,
    the search would fail with `RAG backend requires collection_id`.
    """
    search_mock = _mock_albert_search()

    project = ChatProjectFactory(collection_id="22")
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id="42",
    )
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    api_client.force_authenticate(user=conversation.owner)

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args='{"query": "What does the project doc say?"}',
                )
            }
        else:
            yield "The project doc says hello."

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data={"messages": [ASK_DOC_MESSAGE]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    response_text = b"".join(response.streaming_content).decode("utf-8")
    assert "The project doc says hello." in response_text

    assert search_mock.call_count == 1
    payload = json.loads(search_mock.calls[0].request.content)
    assert payload["collections"] == [22]
    assert payload["prompt"] == "What does the project doc say?"


@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_searches_both_collections_when_conversation_has_own(
    api_client,
    mock_ai_agent_service,
):
    """Conversation with its own collection + project collection → both searched."""
    search_mock = _mock_albert_search()

    project = ChatProjectFactory(collection_id="22")
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id="42",
    )
    conversation = ChatConversationFactory(
        owner=project.owner,
        project=project,
        collection_id="11",
    )
    api_client.force_authenticate(user=conversation.owner)

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args='{"query": "What does the project doc say?"}',
                )
            }
        else:
            yield "Found in both."

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data={"messages": [ASK_DOC_MESSAGE]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    response_text = b"".join(response.streaming_content).decode("utf-8")
    assert search_mock.call_count > 0, f"search not called. response: {response_text!r}"
    payload = json.loads(search_mock.calls[0].request.content)
    assert sorted(payload["collections"]) == [11, 22]


@pytest.fixture(name="inlineable_llm_config")
def _inlineable_llm_config_fixture(settings):
    """Configure a model with enough context to inline a small conversation doc.

    The default test config has no `max_token_context`, which forces every
    document to `tool_call_only`. Override with a 4000-token model and a 0.5
    budget ratio so a tiny conversation attachment lands as ACCESS_FULL_CONTEXT.
    """
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.5
    settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS = 0
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=[],
            max_token_context=4000,
            provider=LLMProvider(
                hrid="unused",
                base_url="https://example.com",
                api_key="key",
            ),
        ),
    }


@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_inlines_convo_doc_while_project_doc_stays_rag_only(
    api_client,
    mock_ai_agent_service,
    inlineable_llm_config,  # pylint: disable=unused-argument
    monkeypatch,
):
    """Hybrid + RAG: convo text doc gets inlined, project doc remains tool-call-only.

    Production scenario: a conversation in a project where the user attaches a
    note directly to the conv AND the project has an indexed
    file. The note must be included in the agent's system prompt (ACCESS_FULL_CONTEXT)
    while the project's collection is searched via the RAG tool.
    """
    search_mock = _mock_albert_search()

    project = ChatProjectFactory(collection_id="22")
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id="42",
    )
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=conversation.owner,
        file_name="note.md",
        content_type="text/markdown",
        conversion_from=None,
        upload_state=AttachmentStatus.READY,
        rag_document_id="43",
    )
    # Avoid touching S3 (causes issues because of the freeze_time ) - feed the
    # builder a tuple (file_name, content) via the same hook as the unit tests .
    note_content = "The conversation note says hello."

    async def fake_read_attachment_content(attachment):
        return attachment.file_name, note_content

    monkeypatch.setattr(
        "chat.document_context_builder.read_attachment_content",
        fake_read_attachment_content,
    )
    api_client.force_authenticate(user=conversation.owner)

    captured_instructions: list[str] = []

    async def agent_model(messages: list[ModelMessage], info: AgentInfo):
        captured_instructions.append(info.instructions or "")
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args='{"query": "What does the project doc say?"}',
                )
            }
        else:
            yield "Done."

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data={"messages": [ASK_DOC_MESSAGE]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    b"".join(response.streaming_content)  # drain the stream

    # Project doc still searched via the RAG tool against project collection.
    assert search_mock.call_count == 1
    payload = json.loads(search_mock.calls[0].request.content)
    assert payload["collections"] == [22]

    # Convo doc reached the system prompt as inlined full context.
    assert captured_instructions, "agent_model never received instructions"
    instructions = captured_instructions[0]
    listing_marker = "List of documents attached to this conversation:\n"
    assert listing_marker in instructions
    listing = json.loads(instructions.split(listing_marker, 1)[1])
    docs_by_title = {d["title"]: d for d in listing["documents"]}

    # Project attachment is RAG-only: never appears in the inlined listing.
    assert set(docs_by_title) == {"note.md"}
    assert docs_by_title["note.md"]["access"] == ACCESS_FULL_CONTEXT
    assert "The conversation note says hello." in docs_by_title["note.md"]["content"]


@respx.mock
@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_does_not_register_rag_for_project_with_only_images(
    api_client,
    hello_conversation_data,
    mock_ai_agent_service,
):
    """A project that only has image attachments must not surface the RAG tool."""
    search_mock = _mock_albert_search()

    project = ChatProjectFactory(collection_id=None)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="image/png",
    )
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    api_client.force_authenticate(user=conversation.owner)

    def agent_model(_messages: list[ModelMessage], info: AgentInfo):
        # Tool is not registered when no indexable attachments exist
        assert "document_search_rag" not in {tool.name for tool in info.function_tools}
        return ModelResponse(parts=[TextPart(content="Hello there")])

    with mock_ai_agent_service(FunctionModel(function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data=hello_conversation_data,
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    assert search_mock.call_count == 0
