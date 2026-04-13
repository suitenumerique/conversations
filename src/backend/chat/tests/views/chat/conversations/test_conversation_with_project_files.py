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
import responses
import respx
from freezegun import freeze_time
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat.factories import (
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
)

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
    return responses.post(
        "https://albert.api.etalab.gouv.fr/v1/search",
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
        status=status.HTTP_200_OK,
    )


@responses.activate
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
    payload = json.loads(search_mock.calls[0].request.body)
    assert payload["collections"] == [22]
    assert payload["prompt"] == "What does the project doc say?"


@responses.activate
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
    payload = json.loads(search_mock.calls[0].request.body)
    assert sorted(payload["collections"]) == [11, 22]


@responses.activate
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
