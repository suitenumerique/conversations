"""Test the media authentication endpoint for chat conversations."""

from io import BytesIO
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

import pytest
import requests
from freezegun import freeze_time

from core.factories import UserFactory

from chat.factories import ChatConversationAttachmentFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def test_api_media_auth_unkown_document(api_client):
    """
    Trying to download a media related to a conversation that does not exist
    should not have the side effect to create it (no regression test).
    """
    ChatConversation.objects.all().delete()

    original_url = f"http://localhost/media/{uuid4()!s}/attachments/{uuid4()!s}.jpg"

    response = api_client.get("/api/v1.0/chats/media-auth/", HTTP_X_ORIGINAL_URL=original_url)

    assert response.status_code == 403
    assert ChatConversation.objects.exists() is False


def test_api_media_auth_anonymous(api_client):
    """
    Users who are not owners of a conversation should not be able to retrieve
    attachments linked to it.
    """
    attachment = ChatConversationAttachmentFactory()

    original_url = f"http://localhost/media/{attachment.key:s}"
    response = api_client.get("/api/v1.0/chats/media-auth/", HTTP_X_ORIGINAL_URL=original_url)

    assert response.status_code == 403
    assert "Authorization" not in response


def test_api_media_auth_owner(api_client):
    """
    Owners of a conversation should be able to retrieve attachments linked to it.
    """
    attachment = ChatConversationAttachmentFactory()

    default_storage.connection.meta.client.put_object(
        Bucket=default_storage.bucket_name,
        Key=attachment.key,
        Body=BytesIO(b"my prose"),
        ContentType="text/plain",
    )

    original_url = f"http://localhost/media/{attachment.key:s}"
    now = timezone.now()
    with freeze_time(now):
        api_client.force_login(attachment.conversation.owner)
        response = api_client.get("/api/v1.0/chats/media-auth/", HTTP_X_ORIGINAL_URL=original_url)

    assert response.status_code == 200

    authorization = response["Authorization"]
    assert "AWS4-HMAC-SHA256 Credential=" in authorization
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature=" in authorization
    assert response["X-Amz-Date"] == now.strftime("%Y%m%dT%H%M%SZ")

    s3_url = urlparse(settings.AWS_S3_ENDPOINT_URL)
    file_url = f"{settings.AWS_S3_ENDPOINT_URL:s}/conversations-media-storage/{attachment.key:s}"
    response = requests.get(
        file_url,
        headers={
            "authorization": authorization,
            "x-amz-date": response["x-amz-date"],
            "x-amz-content-sha256": response["x-amz-content-sha256"],
            "Host": f"{s3_url.hostname:s}:{s3_url.port:d}",
        },
        timeout=1,
    )
    assert response.content.decode("utf-8") == "my prose"


def test_api_media_auth_not_owner(api_client):
    """
    Users who are not owners of a conversation should not be able to retrieve
    attachments linked to it.
    """
    attachment = ChatConversationAttachmentFactory()
    user = UserFactory()

    api_client.force_login(user)
    original_url = f"http://localhost/media/{attachment.key:s}"
    response = api_client.get("/api/v1.0/chats/media-auth/", HTTP_X_ORIGINAL_URL=original_url)

    assert response.status_code == 403
    assert "Authorization" not in response


def test_api_media_auth_owner_missing_attachment(api_client):
    """
    Owners of a conversation should not be able to retrieve attachments
    that are not on the storage.
    """
    attachment = ChatConversationAttachmentFactory()

    original_url = f"http://localhost/media/{attachment.key:s}"
    now = timezone.now()
    with freeze_time(now):
        api_client.force_login(attachment.conversation.owner)
        response = api_client.get("/api/v1.0/chats/media-auth/", HTTP_X_ORIGINAL_URL=original_url)

    assert response.status_code == 403
    assert "Authorization" not in response
