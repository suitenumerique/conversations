"""Tests for the edit_in_docs view action."""

from unittest.mock import MagicMock, patch

from django.utils import formats, timezone

import httpx
import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.factories import ChatConversationFactory
from chat.views.edit_in_docs import (
    _build_doc_title,
    conditional_refresh_oidc_token,
)

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
    return patch("chat.views.edit_in_docs.DocsClient.create_document", mock), mock


# ---------------------------------------------------------------------------
# Authentication / authorisation
# ---------------------------------------------------------------------------
def test_edit_in_docs_unauthenticated(api_client):
    """Unauthenticated requests must receive HTTP 401."""
    conversation = ChatConversationFactory()
    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_edit_in_docs_other_users_conversation(api_client):
    """A user cannot export from another user's conversation — expects HTTP 404."""
    conversation = ChatConversationFactory()
    api_client.force_login(UserFactory())
    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_edit_in_docs_nonexistent_conversation(api_client):
    """Exporting from a nonexistent conversation must return HTTP 404."""
    api_client.force_login(UserFactory())
    url = "/api/v1.0/chats/99999/edit-in-docs/"

    response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------
def test_edit_in_docs_missing_message_id(api_client):
    """Missing message_id in request body must return HTTP 400."""
    conversation = ChatConversationFactory()
    api_client.force_login(conversation.owner)
    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    response = api_client.post(url, data={}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_edit_in_docs_message_not_found(api_client, conversation_with_messages):
    """An unknown message_id must return HTTP 400 with a descriptive error."""
    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)
    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    response = api_client.post(url, data={"message_id": "msg-does-not-exist"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "message_id" in response.json()


def test_edit_in_docs_user_message_not_exportable(api_client, conversation_with_messages):
    """Attempting to export a user message (not assistant) must return HTTP 400."""
    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)
    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    response = api_client.post(url, data={"message_id": "user-message-1"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Successful export
# ---------------------------------------------------------------------------
def test_edit_in_docs_success(api_client, settings, conversation_with_messages):
    """A valid request creates a Docs document and returns 201 with docId and docUrl."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True

    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)

    # Inject an OIDC token into the session via a force-login session override
    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    ctx, mock_create = _mock_docs_create("doc-abc")
    with ctx:
        response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["docId"] == "doc-abc"
    assert data["docUrl"] == "http://docs.example.com/docs/doc-abc/"
    mock_create.assert_called_once()


def test_edit_in_docs_content_joins_text_parts(
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

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    ctx, mock_create = _mock_docs_create()
    with ctx:
        response = api_client.post(url, data={"message_id": "assistant-message-2"}, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["content"] == "Assistant text part 1\n\nAssistant text part 2"


def test_edit_in_docs_falls_back_to_message_content(api_client, settings):
    """A message with no text parts but a populated `content` exports that content.

    Older/hydrated messages carry their text in the deprecated `content` field with
    no text parts; the export must fall back to it (mirrors the frontend gate).
    """
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True

    message = UIMessage(
        id="assistant-hydrated",
        role="assistant",
        content="# Hydrated markdown\n\nBody text",
        parts=[],
    )
    conversation = ChatConversationFactory()
    conversation.messages = [message]
    conversation.save()
    api_client.force_login(conversation.owner)

    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    ctx, mock_create = _mock_docs_create()
    with ctx:
        response = api_client.post(url, data={"message_id": "assistant-hydrated"}, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert mock_create.call_args.kwargs["content"] == "# Hydrated markdown\n\nBody text"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
def test_edit_in_docs_empty_content_returns_400(api_client, settings):
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

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"
    response = api_client.post(url, data={"message_id": "assistant-message-no-text"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "message_id" in response.json()


def test_edit_in_docs_missing_oidc_token_returns_403(
    api_client, settings, conversation_with_messages
):
    """Without an OIDC access token in the session, the view must return HTTP 403."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True
    # Pin refresh-token storage off so the test always exercises the
    # missing-access-token branch instead of the refresh path.
    settings.OIDC_STORE_REFRESH_TOKEN = False

    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)
    # No oidc_access_token is injected into the session.

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_edit_in_docs_docs_service_unavailable_returns_503(
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

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    with patch(
        "chat.views.edit_in_docs.DocsClient.create_document",
        side_effect=httpx.ConnectError("Docs unreachable"),
    ):
        response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "detail" in response.json()


def _http_error(docs_status):
    """Build an httpx.HTTPStatusError carrying a response with the given status."""
    request = httpx.Request("POST", "http://docs.example.com/external_api/v1.0/documents/")
    response = httpx.Response(docs_status, content=b"docs error body", request=request)
    return httpx.HTTPStatusError(f"HTTP {docs_status}", request=request, response=response)


@pytest.mark.parametrize(
    ("docs_status", "expected"),
    [
        (
            status.HTTP_401_UNAUTHORIZED,
            (status.HTTP_401_UNAUTHORIZED, "docs_authentication_expired"),
        ),
        (status.HTTP_403_FORBIDDEN, (status.HTTP_403_FORBIDDEN, None)),
        (status.HTTP_400_BAD_REQUEST, (status.HTTP_502_BAD_GATEWAY, None)),
        (status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, (status.HTTP_502_BAD_GATEWAY, None)),
        (status.HTTP_500_INTERNAL_SERVER_ERROR, (status.HTTP_503_SERVICE_UNAVAILABLE, None)),
    ],
)
def test_edit_in_docs_maps_docs_http_errors(
    api_client, settings, conversation_with_messages, docs_status, expected
):
    """An HTTP error from Docs must map to a meaningful client status, not a blanket 503."""
    expected_status, expected_code = expected
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True

    conversation = conversation_with_messages
    api_client.force_login(conversation.owner)

    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"

    with patch(
        "chat.views.edit_in_docs.DocsClient.create_document",
        side_effect=_http_error(docs_status),
    ):
        response = api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    assert response.status_code == expected_status
    assert "detail" in response.json()
    if expected_code is not None:
        assert response.json()["code"] == expected_code


# ---------------------------------------------------------------------------
# Title (_build_doc_title)
# ---------------------------------------------------------------------------
def test_build_doc_title_is_generic_and_timestamped():
    """The title is the generic template plus the locale's SHORT_DATETIME_FORMAT date."""
    # Format the date on both sides of the call so a minute rollover cannot flake.
    before = formats.date_format(timezone.now(), "SHORT_DATETIME_FORMAT")
    title = _build_doc_title()
    after = formats.date_format(timezone.now(), "SHORT_DATETIME_FORMAT")

    assert title in (
        f"[L'Assistant] New document {before}",
        f"[L'Assistant] New document {after}",
    )


# ---------------------------------------------------------------------------
# OIDC refresh decorator (conditional_refresh_oidc_token)
# ---------------------------------------------------------------------------
def test_conditional_refresh_wraps_when_refresh_enabled(settings):
    """When refresh tokens are stored, the action is wrapped to refresh on demand."""
    settings.OIDC_STORE_REFRESH_TOKEN = True

    def action(*args, **kwargs):
        return None

    assert conditional_refresh_oidc_token(action) is not action


def test_conditional_refresh_passthrough_when_refresh_disabled(settings):
    """When refresh tokens are not stored, the action is returned unchanged."""
    settings.OIDC_STORE_REFRESH_TOKEN = False

    def action(*args, **kwargs):
        return None

    assert conditional_refresh_oidc_token(action) is action


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
def _export_the_message(api_client, conversation, settings, create_document):
    """Drive one edit-in-docs export and return the PostHog capture mock."""
    settings.DOCS_BASE_URL = "http://docs.example.com/"
    settings.OIDC_STORE_ACCESS_TOKEN = True
    settings.POSTHOG_KEY = {"id": "key", "host": "https://posthog.test"}

    api_client.force_login(conversation.owner)
    session = api_client.session
    session["oidc_access_token"] = "test-token"
    session.save()

    url = f"/api/v1.0/chats/{conversation.pk}/edit-in-docs/"
    with (
        patch("chat.views.edit_in_docs.DocsClient.create_document", create_document),
        patch("core.analytics.posthog") as mock_posthog,
    ):
        api_client.post(url, data={"message_id": "assistant-message-1"}, format="json")

    return mock_posthog


def test_edit_in_docs_captures_a_successful_export(
    api_client, settings, conversation_with_messages
):
    """A successful export reports success, attributed to the exporting user."""
    conversation = conversation_with_messages

    mock_posthog = _export_the_message(
        api_client, conversation, settings, MagicMock(return_value={"id": "doc-123"})
    )

    mock_posthog.capture.assert_called_once()
    call = mock_posthog.capture.call_args
    assert call.args[0] == "conversation_exported_to_docs"
    assert call.kwargs["distinct_id"] == str(conversation.owner.pk)
    assert call.kwargs["properties"] == {
        "success": True,
        "outcome": "success",
        "docs_status": None,
    }


def test_edit_in_docs_captures_the_status_docs_answered_with(
    api_client, settings, conversation_with_messages
):
    """The Docs status is only knowable server-side, so the failure event carries it."""
    mock_posthog = _export_the_message(
        api_client,
        conversation_with_messages,
        settings,
        MagicMock(side_effect=_http_error(status.HTTP_403_FORBIDDEN)),
    )

    call = mock_posthog.capture.call_args
    assert call.args[0] == "conversation_exported_to_docs"
    assert call.kwargs["properties"] == {
        "success": False,
        "outcome": "docs_http_error",
        "docs_status": status.HTTP_403_FORBIDDEN,
    }


def test_edit_in_docs_captures_an_unreachable_docs(
    api_client, settings, conversation_with_messages
):
    """A transport failure is reported apart from a Docs-side rejection."""
    mock_posthog = _export_the_message(
        api_client,
        conversation_with_messages,
        settings,
        MagicMock(side_effect=httpx.RequestError("connection refused")),
    )

    call = mock_posthog.capture.call_args
    assert call.kwargs["properties"] == {
        "success": False,
        "outcome": "docs_unreachable",
        "docs_status": None,
    }
