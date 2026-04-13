"""Tests for project attachment views."""

import uuid
from io import BytesIO
from unittest import mock

from django.core.files.storage import default_storage
from django.test import override_settings

import pytest

from core.file_upload.enums import AttachmentStatus, FileUploadMode

from chat import factories, models
from chat.tests.conftest import PIXEL_PNG

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ #
# Create (presigned URL flow)
# ------------------------------------------------------------------ #


def test_project_attachment_create_anonymous_forbidden(api_client):
    """Anonymous users should not be able to create project attachments."""
    project = factories.ChatProjectFactory()
    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    response = api_client.post(url, {"file_name": "test.png", "size": 123}, format="json")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication credentials were not provided."}


def test_project_attachment_create_not_owner_forbidden(api_client):
    """A user who does not own the project should not be able to create an attachment."""
    project = factories.ChatProjectFactory()
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "test.png", "size": 123, "content_type": "image/png"}, format="json"
    )

    assert response.status_code == 404


def test_project_attachment_create_success(api_client):
    """An authenticated user who owns the project should be able to create an attachment."""
    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "test.png", "size": 123, "content_type": "image/png"}, format="json"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["policy"] is not None
    assert data["key"].startswith(f"{project.pk!s}/attachments/")
    assert data["key"].endswith(".png")

    attachment = models.ChatConversationAttachment.objects.get(pk=data["id"])
    assert attachment.project == project
    assert attachment.conversation is None
    assert attachment.uploaded_by == project.owner
    assert attachment.upload_state == AttachmentStatus.PENDING
    assert attachment.file_name == "test.png"
    assert attachment.size == 123


def test_project_attachment_create_size_limit_exceeded(api_client, settings):
    """The attachment should not be created if the file size exceeds the maximum limit."""
    settings.ATTACHMENT_MAX_SIZE = 1024  # 1 KB for test
    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "test.png", "size": 2048, "content_type": "image/png"}, format="json"
    )

    assert response.status_code == 400
    assert response.json() == {"size": ["File size exceeds the maximum limit of 0 MB."]}


# ------------------------------------------------------------------ #
# Retrieve
# ------------------------------------------------------------------ #


def test_project_attachment_retrieve_anonymous_forbidden(api_client):
    """Anonymous users should not be able to retrieve project attachments."""
    attachment = factories.ChatProjectAttachmentFactory()
    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.get(url)

    assert response.status_code == 401


def test_project_attachment_retrieve_not_owner_forbidden(api_client):
    """A user who does not own the project should not be able to retrieve an attachment."""
    attachment = factories.ChatProjectAttachmentFactory()
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/"
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
def test_project_attachment_retrieve_success(api_client, upload_state, expected_url_present):
    """
    An authenticated user who owns the project should be able to retrieve an attachment.
    The URL should be present only for appropriate statuses.
    """
    attachment = factories.ChatProjectAttachmentFactory(upload_state=upload_state)
    api_client.force_login(attachment.project.owner)

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.get(url)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(attachment.pk)
    assert ("url" in data and data["url"] is not None) == expected_url_present


# ------------------------------------------------------------------ #
# Upload ended (presigned URL flow)
# ------------------------------------------------------------------ #


@override_settings(POSTHOG_KEY="test_key")
@mock.patch("chat.views.posthog")
@mock.patch("chat.views.malware_detection.analyse_file")
def test_project_upload_ended_success(mock_analyse_file, mock_posthog, api_client):
    """The 'upload_ended' action should change the attachment state and trigger analysis."""
    attachment = factories.ChatProjectAttachmentFactory(
        upload_state=AttachmentStatus.PENDING,
        file_name="test.txt",
        size=4,
    )
    api_client.force_login(attachment.project.owner)

    # Create a dummy file in storage
    default_storage.connection.meta.client.put_object(
        Bucket=default_storage.bucket_name,
        Key=attachment.key,
        Body=BytesIO(b"my prose"),
        ContentType="text/plain",
    )

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/upload-ended/"
    response = api_client.post(url)

    assert response.status_code == 200
    attachment.refresh_from_db()
    assert attachment.upload_state == AttachmentStatus.ANALYZING
    assert attachment.content_type == "text/plain"

    mock_analyse_file.assert_called_once_with(
        attachment.key,
        safe_callback="chat.malware_detection.project_safe_attachment_callback",
        unknown_callback="chat.malware_detection.project_unknown_attachment_callback",
        unsafe_callback="chat.malware_detection.project_unsafe_attachment_callback",
        project_id=attachment.project.pk,
    )
    mock_posthog.capture.assert_called_once()


def test_project_upload_ended_not_pending(api_client):
    """The 'upload_ended' action should fail if the attachment is not in the PENDING state."""
    attachment = factories.ChatProjectAttachmentFactory(upload_state=AttachmentStatus.ANALYZING)
    api_client.force_login(attachment.project.owner)

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/upload-ended/"
    response = api_client.post(url)

    assert response.status_code == 400
    assert response.json() == {
        "attachment": "This action is only available for items in PENDING state."
    }


def test_project_upload_ended_not_owner(api_client):
    """A user who does not own the project cannot end the upload."""
    attachment = factories.ChatProjectAttachmentFactory(upload_state=AttachmentStatus.PENDING)
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/upload-ended/"
    response = api_client.post(url)

    assert response.status_code == 404


# ------------------------------------------------------------------ #
# Upload mode variants
# ------------------------------------------------------------------ #


def test_project_attachment_create_presigned_url_mode_returns_policy(api_client, settings):
    """Test that presigned_url mode returns policy field."""
    settings.FILE_UPLOAD_MODE = FileUploadMode.PRESIGNED_URL

    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    response = api_client.post(
        url,
        {"file_name": "test.pdf", "size": 1000, "content_type": "application/pdf"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["policy"] is not None
    assert "s3" in data["policy"].lower() or "minio" in data["policy"].lower()


def test_project_attachment_create_backend_to_s3_mode_no_policy(api_client, settings):
    """Test that backend_to_s3 mode does not return policy."""
    settings.FILE_UPLOAD_MODE = FileUploadMode.BACKEND_TO_S3

    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "test.pdf", "content_type": "application/pdf"}, format="json"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["policy"] is None


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #


def test_project_attachment_delete_anonymous_forbidden(api_client):
    """Anonymous users should not be able to delete project attachments."""
    attachment = factories.ChatProjectAttachmentFactory()
    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.delete(url)

    assert response.status_code == 401


def test_project_attachment_delete_not_owner_forbidden(api_client):
    """A user who does not own the project should not be able to delete an attachment."""
    attachment = factories.ChatProjectAttachmentFactory()
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.delete(url)

    assert response.status_code == 404


def test_project_attachment_delete_success(api_client):
    """An authenticated user who owns the project should be able to delete an attachment."""
    attachment = factories.ChatProjectAttachmentFactory()
    api_client.force_login(attachment.project.owner)

    # Create a dummy file in storage
    default_storage.connection.meta.client.put_object(
        Bucket=default_storage.bucket_name,
        Key=attachment.key,
        Body=BytesIO(b"content"),
        ContentType="text/plain",
    )

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.delete(url)

    assert response.status_code == 204
    assert not models.ChatConversationAttachment.objects.filter(pk=attachment.pk).exists()


# ------------------------------------------------------------------ #
# Backend upload (backend_to_s3 flow)
# ------------------------------------------------------------------ #


def test_project_backend_upload_anonymous_forbidden(api_client):
    """Anonymous users should not be able to use backend upload."""
    project = factories.ChatProjectFactory()
    url = f"/api/v1.0/projects/{project.pk!s}/attachments/backend-upload/"

    response = api_client.post(url, {}, format="multipart")
    assert response.status_code == 401


def test_project_backend_upload_not_owner_forbidden(api_client):
    """Users who don't own the project cannot upload via backend."""
    project = factories.ChatProjectFactory()
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(
        url, {"file": file_obj, "file_name": "test.png"}, format="multipart"
    )
    assert response.status_code == 404


@mock.patch("chat.views.malware_detection.analyse_file")
def test_project_backend_upload_success(mock_malware, api_client):
    """Test successful backend file upload for a project."""
    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(
        url, {"file": file_obj, "file_name": "test.png"}, format="multipart"
    )

    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert "key" in data
    assert data["file_name"] == "test.png"
    assert data["size"] == len(PIXEL_PNG)
    assert data["content_type"] == "image/png"

    attachment = models.ChatConversationAttachment.objects.get(pk=data["id"])
    assert attachment.project == project
    assert attachment.conversation is None
    assert attachment.uploaded_by == project.owner

    mock_malware.assert_called_once()


@mock.patch("chat.views.malware_detection.analyse_file")
def test_project_backend_upload_creates_s3_file(_mock_malware, api_client):
    """Test that backend upload creates file in S3."""
    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(
        url, {"file": file_obj, "file_name": "test.png"}, format="multipart"
    )

    assert response.status_code == 201
    data = response.json()
    key = data["key"]

    assert default_storage.exists(key)

    with default_storage.open(key, "rb") as f:
        content = f.read()
    assert content == PIXEL_PNG
