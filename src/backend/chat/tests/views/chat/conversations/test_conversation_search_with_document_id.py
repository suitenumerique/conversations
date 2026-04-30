"""
Test model targets a specific document via document_search_rag(document_id=X)
and the filter propagates all the way to the Albert /v1/search HTTP request body.
"""

import json
from unittest import mock

from django.contrib.sessions.backends.cache import SessionStore
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import httpx
import pytest
import respx
from freezegun import freeze_time
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from rest_framework import status

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure AI service URLs and the Albert backend."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


@pytest.fixture(autouse=True)
def mock_refresh_access_token():
    """Bypass token refresh during the request."""
    with mock.patch("utils.oidc.refresh_access_token") as mocked:
        session = SessionStore()
        session["oidc_access_token"] = "mocked-access-token"
        mocked.return_value = session
        yield mocked


@respx.mock
@freeze_time()
def test_post_conversation_search_with_document_id_filters_albert_request(
    api_client,
    mock_ai_agent_service,
):
    """
    The model picks one of the attached documents from the listing JSON and emits
    document_search_rag(document_id=X). Albert receives a /v1/search POST whose
    body carries metadata_filters with that document's name.
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us", collection_id="123")
    api_client.force_authenticate(user=chat_conversation.owner)

    # Two pre-existing converted attachments. Order_by(created_at, id) makes
    # alpha the older one and beta the newer; the listing reverses to newest-first,
    # so listing.documents[0] is beta.
    alpha = ChatConversationAttachmentFactory(
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        file_name="alpha.pdf.md",
        content_type="text/markdown",
        conversion_from="123/attachments/alpha.pdf",
    )
    beta = ChatConversationAttachmentFactory(
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        file_name="beta.pdf.md",
        content_type="text/markdown",
        conversion_from="123/attachments/beta.pdf",
    )
    default_storage.save(alpha.key, ContentFile(b"alpha document content"))
    default_storage.save(beta.key, ContentFile(b"beta document content"))

    # Mock Albert /v1/search at the wire level so we can inspect the outgoing body.
    albert_search_route = respx.post("https://albert.api.etalab.gouv.fr/v1/search").mock(
        return_value=httpx.Response(
            status.HTTP_200_OK,
            json={
                "data": [
                    {
                        "method": "semantic",
                        "chunk": {
                            "id": 1,
                            "content": "snippet from beta",
                            "metadata": {"document_name": "beta.pdf"},
                        },
                        "score": 0.9,
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
    )

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        if len(messages) == 1:
            # First call: parse the system instructions, find the doc named
            # "beta.pdf" by title, and emit a tool call targeting it.
            # (Title-based lookup avoids dependence on listing order, which is
            # tie-broken by UUID when created_at is frozen by @freeze_time.)
            instructions = messages[0].instructions or ""
            _, _, listing_json = instructions.partition(
                "List of documents attached to this conversation:\n"
            )
            listing = json.loads(listing_json)
            target_document_id = next(
                (doc["document_id"] for doc in listing["documents"] if doc["title"] == "beta.pdf"),
                None,
            )
            assert target_document_id is not None
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args=json.dumps(
                        {"query": "what is in the document?", "document_id": target_document_id}
                    ),
                )
            }
        else:
            yield "It says beta content."

    user_message = UIMessage(
        id="1",
        role="user",
        content="What does the document say?",
        parts=[TextUIPart(text="What does the document say?", type="text")],
    )

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [user_message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    # Drain the stream so side effects complete.
    _ = b"".join(response.streaming_content)  # NOSONAR

    # The Albert search endpoint was called exactly once, with metadata_filters
    # carrying the targeted document's name (beta = newest = listing[0]).
    assert albert_search_route.call_count == 1
    payload = json.loads(albert_search_route.calls[0].request.content)
    assert payload["metadata_filters"] == {
        "key": "document_name",
        "value": "beta.pdf",  # ".md" suffix stripped because alpha/beta are converted
        "type": "eq",
    }
    assert payload["prompt"] == "what is in the document?"
