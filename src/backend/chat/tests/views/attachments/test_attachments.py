"""Tests for chat attachment views."""

import uuid
from io import BytesIO
from unittest import mock

from django.core.files.storage import default_storage
from django.test import override_settings

import pytest

from core.file_upload.enums import AttachmentStatus, FileUploadMode

from chat import factories, models
from chat.enums import AttachmentIndexState
from chat.tests.conftest import PIXEL_PNG

pytestmark = pytest.mark.django_db


def test_attachment_create_anonymous_forbidden(api_client):
    """
    Anonymous users should not be able to create attachments.
    """
    conversation = factories.ChatConversationFactory()
    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/"
    response = api_client.post(url, {"file_name": "test.png", "size": 123}, format="json")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication credentials were not provided."}


def test_attachment_create_authenticated_not_owner_forbidden(api_client):
    """
    A user who does not own the conversation should not be able to create an attachment.
    """
    conversation = factories.ChatConversationFactory()
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "test.png", "size": 123, "content_type": "image/png"}, format="json"
    )

    assert response.status_code == 404


def test_attachment_create_success(api_client):
    """
    An authenticated user who owns the conversation should be able to create an attachment.
    """
    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/"

    response = api_client.post(
        url, {"file_name": "test.png", "size": 123, "content_type": "image/png"}, format="json"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["policy"] is not None
    assert data["key"].startswith(f"{conversation.pk!s}/attachments/")
    assert data["key"].endswith(".png")

    attachment = models.ChatConversationAttachment.objects.get(pk=data["id"])
    assert attachment.conversation == conversation
    assert attachment.uploaded_by == conversation.owner
    assert attachment.upload_state == AttachmentStatus.PENDING
    assert attachment.file_name == "test.png"
    assert attachment.size == 123
    assert attachment.content_type == "image/png"


def test_attachment_create_size_limit_exceeded(api_client, settings):
    """
    The attachment should not be created if the file size exceeds the maximum limit.
    """
    settings.ATTACHMENT_MAX_SIZE = 1024  # 1 KB for test
    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "test.png", "size": 2048, "content_type": "image/png"}, format="json"
    )

    assert response.status_code == 400
    assert response.json() == {"size": ["File size exceeds the maximum limit of 0 MB."]}


def test_attachment_retrieve_anonymous_forbidden(api_client):
    """
    Anonymous users should not be able to retrieve attachments.
    """
    attachment = factories.ChatConversationAttachmentFactory()
    url = f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/{attachment.pk!s}/"
    response = api_client.get(url)

    assert response.status_code == 401


def test_attachment_retrieve_not_owner_forbidden(api_client):
    """
    A user who does not own the conversation should not be able to retrieve an attachment.
    """
    attachment = factories.ChatConversationAttachmentFactory()
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/{attachment.pk!s}/"
    response = api_client.get(url)

    assert response.status_code == 404


@pytest.mark.parametrize(
    "upload_state, expected_url_present",
    [
        (AttachmentStatus.PENDING, False),
        (AttachmentStatus.ANALYZING, False),
        (AttachmentStatus.READY, True),
        (AttachmentStatus.SUSPICIOUS, True),
        (AttachmentStatus.FILE_TOO_LARGE_TO_ANALYZE, True),
    ],
)
def test_attachment_retrieve_success(api_client, upload_state, expected_url_present):
    """
    An authenticated user who owns the conversation should be able to retrieve an attachment.
    The URL should be present only for appropriate statuses.
    """
    attachment = factories.ChatConversationAttachmentFactory(upload_state=upload_state)
    api_client.force_login(attachment.conversation.owner)

    url = f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/{attachment.pk!s}/"
    response = api_client.get(url)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(attachment.pk)
    assert ("url" in data and data["url"] is not None) == expected_url_present


# --------------------------------------------------------------------------- #
# List
#
# The list endpoint (ListModelMixin) exists so the frontend can poll each
# attachment's index_state and gate sending a message until upload-time RAG
# indexing settles. These cover access control + that index_state is exposed.
# --------------------------------------------------------------------------- #


def test_attachment_list_anonymous_forbidden(api_client):
    """Anonymous users cannot list conversation attachments."""
    attachment = factories.ChatConversationAttachmentFactory()
    url = f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/"
    response = api_client.get(url)

    assert response.status_code == 401


def test_attachment_list_scoped_to_owner(api_client):
    """A non-owner lists no attachments (queryset is owner + conversation scoped)."""
    attachment = factories.ChatConversationAttachmentFactory()
    other_user = factories.UserFactory()
    api_client.force_login(other_user)

    url = f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/"
    response = api_client.get(url)

    assert response.status_code == 200
    assert response.json() == []


def test_attachment_list_scoped_to_conversation(api_client):
    """Listing one conversation never returns another conversation's attachments,
    even when both belong to the same owner."""
    owner = factories.UserFactory()
    conversation_a = factories.ChatConversationFactory(owner=owner)
    conversation_b = factories.ChatConversationFactory(owner=owner)
    api_client.force_login(owner)

    attachment_a = factories.ChatConversationAttachmentFactory(conversation=conversation_a)
    attachment_b = factories.ChatConversationAttachmentFactory(conversation=conversation_b)

    response_a = api_client.get(f"/api/v1.0/chats/{conversation_a.pk}/attachments/")
    response_b = api_client.get(f"/api/v1.0/chats/{conversation_b.pk}/attachments/")

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert [item["id"] for item in response_a.json()] == [str(attachment_a.pk)]
    assert [item["id"] for item in response_b.json()] == [str(attachment_b.pk)]


def test_attachment_list_hides_companions_but_keeps_real_markdown(api_client):
    """The internal markdown companion (conversion_from set) is hidden from the
    list, while a genuine user-uploaded .md file (same content_type) stays."""
    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    original = factories.ChatConversationAttachmentFactory(
        conversation=conversation,
        file_name="paper.pdf",
        content_type="application/pdf",
    )
    real_markdown = factories.ChatConversationAttachmentFactory(
        conversation=conversation,
        file_name="notes.md",
        content_type="text/markdown",
    )
    # Hidden companion produced by indexing: same text/markdown type, but
    # conversion_from points back at the original.
    factories.ChatConversationAttachmentFactory(
        conversation=conversation,
        file_name="paper.pdf.md",
        content_type="text/markdown",
        conversion_from=original.key,
    )

    response = api_client.get(f"/api/v1.0/chats/{conversation.pk}/attachments/")

    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.json()}
    assert returned_ids == {str(original.pk), str(real_markdown.pk)}


def test_attachment_list_excludes_project_attachments(api_client):
    """A conversation that belongs to a project does not surface the project's
    attachments in its own list: project attachments are project-scoped (shared
    RAG files), not conversation rows, so they are never conversation_id-matched."""
    project = factories.ChatProjectFactory()
    conversation = factories.ChatConversationFactory(owner=project.owner, project=project)
    api_client.force_login(conversation.owner)

    conversation_attachment = factories.ChatConversationAttachmentFactory(
        conversation=conversation
    )
    # Project-scoped attachment (conversation is null) must not appear here.
    factories.ChatProjectAttachmentFactory(project=project)

    response = api_client.get(f"/api/v1.0/chats/{conversation.pk}/attachments/")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(conversation_attachment.pk)]


def test_attachment_list_exposes_index_state(api_client):
    """The owner lists their attachments with the index_state the frontend polls."""
    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    indexing = factories.ChatConversationAttachmentFactory(
        conversation=conversation,
        content_type="text/plain",
        upload_state=AttachmentStatus.READY,
        index_state=AttachmentIndexState.INDEXING,
    )
    indexed = factories.ChatConversationAttachmentFactory(
        conversation=conversation,
        content_type="text/plain",
        upload_state=AttachmentStatus.READY,
        index_state=AttachmentIndexState.INDEXED,
    )
    # An attachment on another conversation must not leak into this listing.
    factories.ChatConversationAttachmentFactory(
        conversation__owner=conversation.owner,
        content_type="text/plain",
    )

    url = f"/api/v1.0/chats/{conversation.pk}/attachments/"
    response = api_client.get(url)

    assert response.status_code == 200
    data = response.json()
    states_by_id = {item["id"]: item["index_state"] for item in data}
    assert states_by_id == {
        str(indexing.pk): AttachmentIndexState.INDEXING.value,
        str(indexed.pk): AttachmentIndexState.INDEXED.value,
    }


@override_settings(POSTHOG_KEY="test_key")
@mock.patch("chat.views.posthog")
@mock.patch("chat.views.malware_detection.analyse_file")
def test_upload_ended_success(mock_analyse_file, mock_posthog, api_client):
    """
    The 'upload_ended' action should change the attachment state and trigger analysis.
    """
    attachment = factories.ChatConversationAttachmentFactory(
        upload_state=AttachmentStatus.PENDING,
        file_name="test.txt",
        size=4,
    )
    api_client.force_login(attachment.conversation.owner)

    # Create a dummy file in storage
    default_storage.connection.meta.client.put_object(
        Bucket=default_storage.bucket_name,
        Key=attachment.key,
        Body=BytesIO(b"my prose"),
        ContentType="text/plain",
    )

    url = (
        f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/{attachment.pk!s}/upload-ended/"
    )
    response = api_client.post(url)

    assert response.status_code == 200
    attachment.refresh_from_db()
    assert attachment.upload_state == AttachmentStatus.ANALYZING
    assert attachment.content_type == "text/plain"

    mock_analyse_file.assert_called_once_with(
        attachment.key,
        safe_callback="chat.malware_detection.conversation_safe_attachment_callback",
        unknown_callback="chat.malware_detection.unknown_attachment_callback",
        unsafe_callback="chat.malware_detection.conversation_unsafe_attachment_callback",
        conversation_id=attachment.conversation.pk,
    )
    mock_posthog.capture.assert_called_once()


def test_upload_ended_not_pending(api_client):
    """
    The 'upload_ended' action should fail if the attachment is not in the PENDING state.
    """
    attachment = factories.ChatConversationAttachmentFactory(
        upload_state=AttachmentStatus.ANALYZING
    )
    api_client.force_login(attachment.conversation.owner)

    url = (
        f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/{attachment.pk!s}/upload-ended/"
    )
    response = api_client.post(url)

    assert response.status_code == 400
    assert response.json() == {
        "attachment": "This action is only available for items in PENDING state."
    }


def test_upload_ended_not_owner(api_client):
    """
    A user who does not own the conversation cannot end the upload.
    """
    attachment = factories.ChatConversationAttachmentFactory(upload_state=AttachmentStatus.PENDING)
    user = factories.UserFactory()
    api_client.force_login(user)

    url = (
        f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/{attachment.pk!s}/upload-ended/"
    )
    response = api_client.post(url)

    assert response.status_code == 404


@pytest.mark.parametrize(
    "name,content,_extension,content_type",
    [
        ("test.exe", b"text", "exe", "text/plain"),
        ("test", b"text", "txt", "text/plain"),
        ("test.aaaaaa", b"test", "txt", "text/plain"),
        ("test.txt", PIXEL_PNG, "txt", "image/png"),
        ("test.py", b"#!/usr/bin/python", "py", "text/plain"),
    ],
)
def test_upload_ended_fix_extension(api_client, name, content, _extension, content_type):
    """
    The 'upload_ended' action should update the attachment's file_name, content_type, and size
    based on the actual uploaded file.
    """
    conversation = factories.ChatConversationFactory()
    attachment = factories.ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.PENDING,
        file_name=name,
        size=0,
        key=f"{conversation.pk!s}/attachments/temp-{uuid.uuid4()!s}-{name:s}",
        content_type="application/wrong",
    )

    # Create a dummy file in storage
    default_storage.connection.meta.client.put_object(
        Bucket=default_storage.bucket_name,
        Key=attachment.key,
        Body=content,
        ContentType=content_type,
    )

    api_client.force_login(conversation.owner)
    url = (
        f"/api/v1.0/chats/{attachment.conversation.pk}/attachments/{attachment.pk!s}/upload-ended/"
    )
    response = api_client.post(url)

    assert response.status_code == 200
    attachment.refresh_from_db()

    assert attachment.upload_state == AttachmentStatus.READY  # malware_detection mocked to safe
    assert attachment.content_type == content_type  # updated
    assert attachment.file_name == name  # updated
    assert attachment.size == len(content)  # updated


def test_attachment_create_presigned_url_mode_returns_policy(api_client, settings):
    """Test that presigned_url mode returns policy field."""
    settings.FILE_UPLOAD_MODE = FileUploadMode.PRESIGNED_URL

    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/"
    response = api_client.post(
        url,
        {"file_name": "test.pdf", "size": 1000, "content_type": "application/pdf"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["policy"] is not None
    assert "s3" in data["policy"].lower() or "minio" in data["policy"].lower()


def test_attachment_create_backend_to_s3_mode_no_policy(api_client, settings):
    """Test that backend_to_s3 mode does not return policy."""
    settings.FILE_UPLOAD_MODE = FileUploadMode.BACKEND_TO_S3

    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "test.pdf", "content_type": "application/pdf"}, format="json"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["policy"] is None
