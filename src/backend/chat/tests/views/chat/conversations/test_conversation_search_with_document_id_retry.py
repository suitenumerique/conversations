"""
Test the user-visible behavior of the silent-fallback removal:

1. Model calls documet_search_rag(document_id=X) on a doc that has no matches.
2. Albert returns empty data.
3. The tool raises ModelRetry with a broaden/disclaim message.
4. pydantic-ai re-run the model with the retry feedback
5. the model retries without document_id (broadens the search).
6. Albert returns results this time
7. the model produces a final answer using those results

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
        session["oidc_access_token"] = "mocked-access-function"
        mocked.return_value = session
        yield mocked


@respx.mock
@freeze_time()
def test_post_conversation_filtered_empty_triggers_model_retry_then_unfiltered(
    api_client,
    mock_ai_agent_service,
):
    """
    The Albert search returns empty when filtered by document_name;  tool
    raises ModelRetry;  model re-run and retries without the filter,
    receives real results the 2nd time
    """
    chat_conversation = ChatConversationFactory(owner__language="en-us", collection_id="123")
    api_client.force_authenticate(user=chat_conversation.owner)

    # Create `other` first (becomes oldest), then `target` (becomes newest).
    # The listing is rendered newest-first, so listing[0] is `target`.
    other = ChatConversationAttachmentFactory(
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        file_name="other.pdf.md",
        content_type="text/markdown",
        conversion_from="123/attachments/other.pdf",
    )
    target = ChatConversationAttachmentFactory(
        conversation=chat_conversation,
        uploaded_by=chat_conversation.owner,
        file_name="targeted.pdf.md",
        content_type="text/markdown",
        conversion_from="123/attachments/targeted.pdf",
    )
    default_storage.save(other.key, ContentFile(b"other content"))
    default_storage.save(target.key, ContentFile(b"targeted content"))

    # Albert handler: empty for filtered queries, results for unfiltered.
    def search_handler(request):
        body = json.loads(request.content)
        if "metadata_filters" in body:
            return httpx.Response(
                status.HTTP_200_OK,
                json={
                    "data": [],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 0},
                },
            )
        return httpx.Response(
            status.HTTP_200_OK,
            json={
                "data": [
                    {
                        "method": "semantic",
                        "chunk": {
                            "id": 7,
                            "content": "fallback snippet from collection",
                            "metadata": {"document_name": "other.pdf"},
                        },
                        "score": 0.8,
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            },
        )

    albert_search_route = respx.post("https://albert.api.etalab.gouv.fr/v1/search").mock(
        side_effect=search_handler
    )

    # The model is called three times:
    #   1. Initial: emit a tool call with document_id (filter -> empty -> ModelRetry).
    #   2. After ModelRetry: emit the same query without document_id (broaden).
    #   3. After unfiltered results land: emit the final user-facing text.
    call_count = {"n": 0}

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Find the targeted doc by title rather than listing position;
            # @freeze_time makes the secondary UUID sort key non-deterministic.
            instructions = messages[0].instructions or ""
            _, _, listing_json = instructions.partition(
                "List of documents attached to this conversation:\n"
            )
            listing = json.loads(listing_json)
            target_document_id = next(
                (
                    doc["document_id"]
                    for doc in listing["documents"]
                    if doc["title"] == "targeted.pdf"
                ),
                None,
            )
            assert target_document_id is not None
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args=json.dumps(
                        {"query": "what is the deadline?", "document_id": target_document_id}
                    ),
                )
            }
        elif call_count["n"] == 2:
            yield {
                0: DeltaToolCall(
                    name="document_search_rag",
                    json_args=json.dumps({"query": "what is the deadline?"}),
                )
            }
        else:
            # Compliant with the ModelRetry instruction: when broadening, the
            # model must disclose that the targeted document had no matches and
            # that the search was broadened.
            yield (
                "The targeted document did not contain the requested information, "
                "so I broadened the search to the full collection. "
                "The deadline is mentioned in other.pdf."
            )

    user_message = UIMessage(
        id="1",
        role="user",
        content="What is the deadline?",
        parts=[TextUIPart(text="What is the deadline?", type="text")],
    )

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [user_message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    streamed = b"".join(response.streaming_content).decode("utf-8")

    # The model was driven through all three iterations.
    assert call_count["n"] == 3

    # Two HTTP calls to Albert: first filtered, second unfiltered.
    assert albert_search_route.call_count == 2

    first_payload = json.loads(albert_search_route.calls[0].request.content)
    second_payload = json.loads(albert_search_route.calls[1].request.content)
    assert first_payload["metadata_filters"]["value"] == "targeted.pdf"
    assert "metadata_filters" not in second_payload

    # The user-facing stream contains the final answer (sourced from the unfiltered
    # results) - not an empty/confusing response from the filtered miss.
    streamed_lower = streamed.lower()
    assert "the deadline is mentioned in other.pdf" in streamed_lower
    # The model complies with the ModelRetry instruction: it discloses that the
    # targeted document had no matches and that the search was broadened.
    assert "did not contain" in streamed_lower
    assert "broadened" in streamed_lower
