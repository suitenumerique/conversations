"""Tests for file upload mode `backend_to_s3`."""

from io import BytesIO
from unittest import mock

from django.core.files.storage import default_storage

import pytest

from chat import factories, models
from chat.tests.conftest import PIXEL_PNG

pytestmark = pytest.mark.django_db


def test_backend_upload_anonymous_forbidden(api_client):
    """Anonymous users should not be able to use backend upload."""
    conversation = factories.ChatConversationFactory()
    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/backend-upload/"

    response = api_client.post(url, {}, format="multipart")
    assert response.status_code == 401


def test_backend_upload_not_owner_forbidden(api_client):
    """Users who don't own the conversation cannot upload via backend."""
    conversation = factories.ChatConversationFactory()
    user = factories.UserFactory()
    api_client.force_login(user)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(url, {"file": file_obj, "file_name": "test.png"}, format="multipart")
    assert response.status_code == 404


@mock.patch("chat.views.malware_detection.analyse_file")
def test_backend_upload_success(mock_malware, api_client):
    """Test successful backend file upload."""
    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(url, {"file": file_obj, "file_name": "test.png"}, format="multipart")

    assert response.status_code == 201
    data = response.json()

    # Verify response structure
    assert "id" in data
    assert "key" in data
    assert data["file_name"] == "test.png"
    assert data["size"] == len(PIXEL_PNG)
    assert data["content_type"] == "image/png"

    # Verify attachment was created
    attachment = models.ChatConversationAttachment.objects.get(pk=data["id"])
    assert attachment.conversation == conversation
    assert attachment.uploaded_by == conversation.owner
    assert attachment.file_name == "test.png"
    assert attachment.size == len(PIXEL_PNG)

    # Verify malware detection was called
    mock_malware.assert_called_once()


def test_backend_upload_missing_file(api_client):
    """Test that backend upload fails without file field."""
    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/backend-upload/"

    response = api_client.post(
        url,
        {"file_name": "test.png"},  # No file field
        format="multipart",
    )

    assert response.status_code == 400
    assert "file" in response.json()


@mock.patch("chat.views.malware_detection.analyse_file")
def test_backend_upload_creates_s3_file(_mock_malware, api_client):
    """Test that backend upload creates file in S3."""

    conversation = factories.ChatConversationFactory()
    api_client.force_login(conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(url, {"file": file_obj, "file_name": "test.png"}, format="multipart")

    assert response.status_code == 201
    data = response.json()
    key = data["key"]

    # Verify file exists in S3
    assert default_storage.exists(key)

    # Verify file content
    with default_storage.open(key, "rb") as f:
        content = f.read()
    assert content == PIXEL_PNG
