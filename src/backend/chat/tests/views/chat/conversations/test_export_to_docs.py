"""Tests for the export_to_docs view action."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from rest_framework import status

from core.factories import UserFactory

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@pytest.fixture(name="assistant_message")
def assistant_message_fixture():
    """Build a UIMessage with a single TextUIPart for use in conversation.messages."""
    return UIMessage(
        id="assistant-message-1",
        role="assistant",
        content="Assistant text",
        parts=[TextUIPart(type="text", text="Assistant text")],
    )


@pytest.fixture(name="user_message")
def user_message_fixture():
    """Build a user UIMessage."""
    return UIMessage(
        id="user-message-1",
        role="user",
        content="User text",
        parts=[TextUIPart(type="text", text="User text")],
    )


@pytest.fixture(name="assistant_message_with_multiple_text_parts")
def assistant_message_with_multiple_text_parts_fixture():
    """Build a UIMessage with a multi Part TextUIPart for use in conversation.messages."""
    return UIMessage(
        id="assistant-message-2",
        role="assistant",
        content="Assistant text",
        parts=[
            TextUIPart(type="text", text="Assistant text part 1"),
            TextUIPart(type="text", text="Assistant text part 2"),
        ],
    )


@pytest.fixture(name="conversation_with_messages")
def conversation_with_messages_fixture(assistant_message, user_message):
    """Create a ChatConversation with the given messages."""
    conversation = ChatConversationFactory()
    conversation.messages = [assistant_message, user_message]
    conversation.save()
    return conversation


def _mock_docs_create(doc_id="doc-123"):
    """Return a patch context for DocsClient.create_document."""
    mock = MagicMock(return_value={"id": doc_id})
    return patch("chat.views.DocsClient.create_document", mock), mock


# ---------------------------------------------------------------------------
# Authentication / authorisation
# ---------------------------------------------------------------------------
def test_export_to_docs_unauthenticated(api_client):
    """Unauthenticated requests must receive HTTP 401."""
    conversation = ChatConversationFactory()
    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_export_to_docs_other_users_conversation(api_client):
    """A user cannot export from another user's conversation — expects HTTP 404."""
    conversation = ChatConversationFactory()
    api_client.force_login(UserFactory())
    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_export_to_docs_nonexistent_conversation(api_client):
    """Exporting from a nonexistent conversation must return HTTP 404."""
    api_client.force_login(UserFactory())
    url = "/api/v1.0/chats/99999/export-to-docs/"

    response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------
def test_export_to_docs_missing_message_id(api_client):
    """Missing message_id in request body must return HTTP 400."""
    conversation = ChatConversationFactory()
    api_client.force_login(conversation.owner)
    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    response = api_client.post(url, data={}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_export_to_docs_message_not_found(api_client, conversation_with_messages):
    """An unknown message_id must return HTTP 400 with a descriptive error."""
    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)
    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    response = api_client.post(url, data={"message_id": "msg-does-not-exist"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "message_id" in response.json()


def test_export_to_docs_user_message_not_exportable(api_client, conversation_with_messages):
    """Attempting to export a user message (not assistant) must return HTTP 400."""
    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)
    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    response = api_client.post(url, data={"message_id": "user-message-1"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Successful export
# ---------------------------------------------------------------------------
def test_export_to_docs_success(api_client, settings, conversation_with_messages):
    """A valid request creates a Docs document and returns 201 with docId and docUrl."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True

    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)

    # Inject an OIDC token into the session via a force-login session override
    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    ctx, mock_create = _mock_docs_create("doc-abc")
    with ctx:
        response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["docId"] == "doc-abc"
    assert data["docUrl"] == "http://docs.example.com/doc-abc"
    mock_create.assert_called_once()


def test_export_to_docs_content_joins_text_parts(
    api_client, settings, assistant_message_with_multiple_text_parts
):
    """Content passed to create_document must join all text parts with double newlines."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True

    conversation = ChatConversationFactory()
    conversation.messages = [assistant_message_with_multiple_text_parts]
    conversation.save()
    api_client.force_login(conversation.owner)

    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    ctx, mock_create = _mock_docs_create()
    with ctx:
        api_client.post(url, data={"message_id": "assistant-message-2"}, format="json")

    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["content"] == "Assistant text part 1\n\nAssistant text part 2"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
def test_export_to_docs_empty_content_returns_400(api_client, settings):
    """An assistant message with no text parts must return HTTP 400."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True

    # Message has no text parts — only a source-type part
    message = UIMessage(
        id="assistant-message-no-text",
        role="assistant",
        content="",
        parts=[],
    )
    conversation = ChatConversationFactory()
    conversation.messages = [message]
    conversation.save()
    api_client.force_login(conversation.owner)

    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"
    response = api_client.post(url, data={"message_id": "assistant-message-no-text"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "message_id" in response.json()


def test_export_to_docs_docs_service_unavailable_returns_503(
    api_client, settings, conversation_with_messages
):
    """When the Docs service raises a network error, the view must return HTTP 503."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True

    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)

    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/export-to-docs/"

    with patch(
        "chat.views.DocsClient.create_document",
        side_effect=requests.exceptions.ConnectionError("Docs unreachable"),
    ):
        response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "detail" in response.json()
