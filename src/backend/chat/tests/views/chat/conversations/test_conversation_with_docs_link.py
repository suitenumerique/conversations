"""Conversation endpoint tests for reading pasted La Suite Docs links."""

import uuid
from io import BytesIO

from django.core.files.storage import default_storage

import httpx
import pytest
import respx
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel
from rest_framework import status

from core.feature_flags.flags import FeatureToggle

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.models import ChatConversationAttachment

# transaction=True: the turn runs in another thread and must see the test data.
pytestmark = pytest.mark.django_db(transaction=True)

DOCS_BASE_URL = "https://docs.example.com/"
DOCUMENT_ID = uuid.UUID("0b8f1e9a-3c5d-4e2f-9a1b-7c6d5e4f3a21")
OTHER_DOCUMENT_ID = uuid.UUID("5a4b3c2d-1e0f-4a9b-8c7d-6e5f4a3b2c1d")
ALBERT_URL = "https://albert.api.etalab.gouv.fr/v1"


def _formatted_content_url(document_id):
    """Docs external API endpoint returning a document as markdown."""
    return (
        f"{DOCS_BASE_URL}external_api/v1.0/documents/{document_id}/formatted-content/"
        "?content_format=markdown"
    )


def _docs_response(content="# Meeting notes\n\nThe budget is 42 euros.", title="Meeting notes"):
    """A successful formatted-content response."""
    return httpx.Response(
        status.HTTP_200_OK,
        json={
            "id": str(DOCUMENT_ID),
            "title": title,
            "content": content,
            "created_at": "2026-10-01T10:00:00Z",
            "updated_at": "2026-10-02T12:30:00Z",
        },
    )


@pytest.fixture(autouse=True)
def docs_settings(settings, feature_flags):
    """Enable Docs link fetching against a mocked Docs and Albert RAG backend.

    The model has enough context for a small snapshot to be inlined in its instructions.
    """
    settings.DOCS_BASE_URL = DOCS_BASE_URL
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
            provider=LLMProvider(hrid="unused", base_url="https://example.com", api_key="key"),
        ),
    }
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    feature_flags.docs_link_fetching = FeatureToggle.ENABLED
    feature_flags.document_upload = FeatureToggle.ENABLED
    return settings


@pytest.fixture(name="albert_api")
def albert_api_fixture():
    """Mock the Albert collection and document endpoints."""
    respx.post(f"{ALBERT_URL}/collections").mock(
        return_value=httpx.Response(status.HTTP_200_OK, json={"id": "123"})
    )
    respx.post(f"{ALBERT_URL}/documents").mock(
        return_value=httpx.Response(status.HTTP_201_CREATED, json={"id": 456})
    )


@pytest.fixture(name="conversation")
def conversation_fixture(api_client):
    """A conversation whose owner is logged in with an OIDC access token."""
    conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_login(conversation.owner)
    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()
    return conversation


@pytest.fixture(name="model_instructions")
def model_instructions_fixture(mock_ai_agent_service):
    """Run the turn on a fake model and collect the instructions it receives."""
    received = []

    async def agent_model(_messages: list[ModelMessage], info: AgentInfo):
        received.append(info.instructions)
        yield "Here is my answer."

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        yield received


def _post_message(api_client, conversation, text):
    """Post a user message and return the fully streamed response body."""
    message = UIMessage(
        id="1", role="user", content=text, parts=[TextUIPart(type="text", text=text)]
    )
    response = api_client.post(
        f"/api/v1.0/chats/{conversation.pk}/conversation/",
        data={"messages": [message.model_dump(mode="json")]},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    return b"".join(response.streaming_content).decode("utf-8")


@respx.mock
def test_docs_link_flag_disabled_does_not_call_docs(
    api_client, conversation, feature_flags, model_instructions
):
    """With the flag off, a pasted Docs link is left untouched."""
    feature_flags.docs_link_fetching = FeatureToggle.DISABLED
    docs_route = respx.get(_formatted_content_url(DOCUMENT_ID)).mock(return_value=_docs_response())

    content = _post_message(
        api_client, conversation, f"Summarize {DOCS_BASE_URL}docs/{DOCUMENT_ID}/"
    )

    assert not docs_route.called
    assert "document_parsing" not in content
    assert model_instructions
    assert not ChatConversationAttachment.objects.filter(conversation=conversation).exists()


@respx.mock
def test_docs_link_success_creates_indexed_snapshot(
    api_client,
    conversation,
    albert_api,  # pylint: disable=unused-argument
    model_instructions,
):
    """A readable Docs link becomes an indexed attachment whose content reaches the model."""
    docs_route = respx.get(_formatted_content_url(DOCUMENT_ID)).mock(return_value=_docs_response())

    content = _post_message(
        api_client, conversation, f"Summarize {DOCS_BASE_URL}docs/{DOCUMENT_ID}/ please"
    )

    assert docs_route.call_count == 1
    assert docs_route.calls[0].request.headers["Authorization"] == "Bearer test-token"
    assert (
        f'"toolName":"document_parsing","input":{{"documents":'
        f'[{{"identifier":"{DOCS_BASE_URL}docs/{DOCUMENT_ID}/"}}]}}'
    ) in content
    assert '"output":{"state":"done"}' in content

    attachment = ChatConversationAttachment.objects.get(conversation=conversation)
    assert attachment.docs_document_id == DOCUMENT_ID
    assert attachment.docs_updated_at.isoformat() == "2026-10-02T12:30:00+00:00"
    assert attachment.file_name == "Meeting notes.md"
    assert attachment.content_type == "text/markdown"
    assert attachment.upload_state == "ready"
    assert attachment.uploaded_by == conversation.owner
    assert attachment.key.startswith(f"{conversation.pk}/attachments/")
    assert attachment.rag_document_id == "456"
    assert attachment.is_indexed
    with default_storage.open(attachment.key, "rb") as file:
        assert file.read() == b"# Meeting notes\n\nThe budget is 42 euros."

    assert "The budget is 42 euros." in model_instructions[0]


@respx.mock
def test_docs_link_success_tells_model_link_was_read(
    api_client,
    conversation,
    albert_api,  # pylint: disable=unused-argument
    model_instructions,
):
    """The model is told which attached document the pasted link points to."""
    respx.get(_formatted_content_url(DOCUMENT_ID)).mock(return_value=_docs_response())

    _post_message(api_client, conversation, f"Read {DOCS_BASE_URL}docs/{DOCUMENT_ID}/")

    assert (
        f"The Docs document linked at {DOCS_BASE_URL}docs/{DOCUMENT_ID}/ has been read and "
        'attached to this conversation as "Meeting notes.md".'
    ) in model_instructions[0]


@respx.mock
def test_docs_link_repaste_replaces_snapshot(
    api_client,
    conversation,
    albert_api,  # pylint: disable=unused-argument
    model_instructions,
):
    """Pasting a link again deletes the old snapshot (RAG, S3, row) and keeps only the new one."""
    conversation.collection_id = "123"
    conversation.save()
    old_key = f"{conversation.pk}/attachments/{uuid.uuid4()}.md"
    default_storage.save(old_key, BytesIO(b"Old content"))
    old_attachment = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=conversation.owner,
        key=old_key,
        file_name="Meeting notes.md",
        content_type="text/markdown",
        upload_state="ready",
        rag_document_id="111",
        is_indexed=True,
        docs_document_id=DOCUMENT_ID,
    )
    rag_delete_route = respx.delete(f"{ALBERT_URL}/documents/111").mock(
        return_value=httpx.Response(status.HTTP_204_NO_CONTENT)
    )
    respx.get(_formatted_content_url(DOCUMENT_ID)).mock(
        return_value=_docs_response(content="The budget is now 50 euros.")
    )

    _post_message(api_client, conversation, f"Again: {DOCS_BASE_URL}docs/{DOCUMENT_ID}/")

    assert rag_delete_route.call_count == 1
    assert not default_storage.exists(old_key)
    assert not ChatConversationAttachment.objects.filter(pk=old_attachment.pk).exists()
    attachment = ChatConversationAttachment.objects.get(
        conversation=conversation, docs_document_id=DOCUMENT_ID
    )
    with default_storage.open(attachment.key, "rb") as file:
        assert file.read() == b"The budget is now 50 euros."
    assert "The budget is now 50 euros." in model_instructions[0]
    assert "Old content" not in model_instructions[0]


@respx.mock
def test_docs_link_forbidden_does_not_abort_turn(
    api_client, conversation, model_instructions, caplog
):
    """A 403 from Docs becomes a note for the model and the turn still answers."""
    respx.get(_formatted_content_url(DOCUMENT_ID)).mock(
        return_value=httpx.Response(status.HTTP_403_FORBIDDEN)
    )

    content = _post_message(api_client, conversation, f"Read {DOCS_BASE_URL}docs/{DOCUMENT_ID}/")

    assert '"output":{"state":"done"}' in content
    assert "Here is my answer." in content
    assert (
        f"The Docs document linked at {DOCS_BASE_URL}docs/{DOCUMENT_ID}/ could not be read: "
        "the user does not have access to this document."
    ) in model_instructions[0]
    assert "formatted_content" in caplog.text
    assert not ChatConversationAttachment.objects.filter(conversation=conversation).exists()


@respx.mock
def test_docs_links_mixed_success_and_failure(
    api_client,
    conversation,
    albert_api,  # pylint: disable=unused-argument
    model_instructions,
):
    """A readable link is used even when another link of the same message fails."""
    respx.get(_formatted_content_url(DOCUMENT_ID)).mock(return_value=_docs_response())
    respx.get(_formatted_content_url(OTHER_DOCUMENT_ID)).mock(
        return_value=httpx.Response(status.HTTP_404_NOT_FOUND)
    )

    content = _post_message(
        api_client,
        conversation,
        f"Compare {DOCS_BASE_URL}docs/{DOCUMENT_ID}/ and {DOCS_BASE_URL}docs/{OTHER_DOCUMENT_ID}/",
    )

    assert "Here is my answer." in content
    attachment = ChatConversationAttachment.objects.get(conversation=conversation)
    assert attachment.docs_document_id == DOCUMENT_ID
    assert "The budget is 42 euros." in model_instructions[0]
    assert (
        f"{DOCS_BASE_URL}docs/{OTHER_DOCUMENT_ID}/ could not be read: "
        "the document does not exist or has been deleted."
    ) in model_instructions[0]


@respx.mock
def test_docs_link_oversize_document_rejected(
    api_client, conversation, settings, model_instructions
):
    """A document over ATTACHMENT_MAX_SIZE is not stored and the model is told why."""
    settings.ATTACHMENT_MAX_SIZE = 10
    respx.get(_formatted_content_url(DOCUMENT_ID)).mock(return_value=_docs_response())

    content = _post_message(api_client, conversation, f"Read {DOCS_BASE_URL}docs/{DOCUMENT_ID}/")

    assert "Here is my answer." in content
    assert "the document is too large to be read." in model_instructions[0]
    assert not ChatConversationAttachment.objects.filter(conversation=conversation).exists()
