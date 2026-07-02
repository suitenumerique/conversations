"""Tests for project attachment views."""

import logging
from io import BytesIO
from unittest import mock

from django.core.files.storage import default_storage
from django.test import override_settings

import pytest
import responses
from rest_framework import status as http_status

from core.file_upload.enums import AttachmentStatus, FileUploadMode

from chat import factories, models
from chat.enums import AttachmentIndexState
from chat.tests.conftest import PIXEL_PNG

pytestmark = pytest.mark.django_db


@pytest.fixture(name="albert_settings")
def fixture_albert_settings(settings):
    """Configure Albert backend so per-document delete hits a known URL."""
    return settings


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


def test_project_attachment_create_files_cap(api_client, settings):
    """A project at the files cap rejects further non-image uploads with 400."""
    settings.PROJECT_FILES_MAX_COUNT = 2
    project = factories.ChatProjectFactory()
    factories.ChatProjectAttachmentFactory(project=project, content_type="application/pdf")
    factories.ChatProjectAttachmentFactory(project=project, content_type="text/plain")
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    response = api_client.post(
        url, {"file_name": "third.pdf", "content_type": "application/pdf"}, format="json"
    )

    assert response.status_code == 400
    assert "maximum of 2 files" in response.json()["content_type"][0]


def test_project_attachment_create_images_cap(api_client, settings):
    """A project at the images cap rejects further image uploads but allows non-images."""
    settings.PROJECT_IMAGES_MAX_COUNT = 1
    settings.PROJECT_FILES_MAX_COUNT = 99  # don't trip the files cap in this test
    project = factories.ChatProjectFactory()
    factories.ChatProjectAttachmentFactory(project=project, content_type="image/png")
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"

    over_cap = api_client.post(
        url, {"file_name": "second.jpg", "content_type": "image/jpeg"}, format="json"
    )
    assert over_cap.status_code == 400
    assert "maximum of 1 images" in over_cap.json()["content_type"][0]

    # A non-image upload still goes through - the caps are independent.
    pdf_ok = api_client.post(
        url, {"file_name": "doc.pdf", "content_type": "application/pdf"}, format="json"
    )
    assert pdf_ok.status_code == 201


def test_project_attachment_create_companion_rows_excluded_from_caps(api_client, settings):
    """Hidden markdown companion rows do not count against either cap."""
    settings.PROJECT_FILES_MAX_COUNT = 1
    project = factories.ChatProjectFactory()
    original = factories.ChatProjectAttachmentFactory(
        project=project, content_type="application/pdf"
    )
    factories.ChatProjectAttachmentFactory(
        project=project,
        key=original.key,
        file_name=f"{original.file_name}.md",
        content_type="text/markdown",
        conversion_from=original.key,
    )
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/"
    # Original counts as 1, companion is excluded -> still at the cap (1/1).
    response = api_client.post(
        url, {"file_name": "another.pdf", "content_type": "application/pdf"}, format="json"
    )

    assert response.status_code == 400
    assert "maximum of 1 files" in response.json()["content_type"][0]


@mock.patch("chat.views.attachments.malware_detection.analyse_file")
def test_project_backend_upload_files_cap(_mock_malware, api_client, settings):
    """The cap is enforced before the S3 upload on the backend-upload path."""
    settings.PROJECT_FILES_MAX_COUNT = 1
    project = factories.ChatProjectFactory()
    factories.ChatProjectAttachmentFactory(project=project, content_type="application/pdf")
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(b"%PDF-1.4 fake bytes")
    file_obj.name = "second.pdf"

    response = api_client.post(
        url,
        {"file": file_obj, "file_name": "second.pdf"},
        format="multipart",
    )

    assert response.status_code == 400
    assert "maximum of 1 files" in response.json()["content_type"][0]


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
@mock.patch("chat.views.attachments.posthog")
@mock.patch("chat.views.attachments.malware_detection.analyse_file")
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


@responses.activate
def test_project_attachment_delete_drops_rag_document(api_client, albert_settings):
    """Deleting an indexed attachment removes its document from the RAG collection."""
    project = factories.ChatProjectFactory(collection_id="42")
    attachment = factories.ChatProjectAttachmentFactory(
        project=project,
        rag_document_id="123",
    )
    api_client.force_login(project.owner)
    delete_doc_mock = responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/documents/123",
        status=http_status.HTTP_204_NO_CONTENT,
    )

    url = f"/api/v1.0/projects/{project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.delete(url)

    assert response.status_code == 204
    assert delete_doc_mock.call_count == 1
    assert not models.ChatConversationAttachment.objects.filter(pk=attachment.pk).exists()


@responses.activate
def test_project_attachment_delete_skips_backend_when_no_doc_id(api_client, albert_settings):
    """An attachment without rag_document_id (image, Find backend) skips the backend call."""
    project = factories.ChatProjectFactory(collection_id="42")
    attachment = factories.ChatProjectAttachmentFactory(
        project=project,
        rag_document_id=None,
    )
    api_client.force_login(project.owner)
    delete_doc_mock = responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/documents/anything",
        status=http_status.HTTP_204_NO_CONTENT,
    )

    url = f"/api/v1.0/projects/{project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.delete(url)

    assert response.status_code == 204
    assert delete_doc_mock.call_count == 0
    assert not models.ChatConversationAttachment.objects.filter(pk=attachment.pk).exists()


@responses.activate
def test_project_attachment_delete_succeeds_when_backend_fails(api_client, albert_settings, caplog):
    """A backend failure is logged but does not block the attachment delete."""
    project = factories.ChatProjectFactory(collection_id="42")
    attachment = factories.ChatProjectAttachmentFactory(
        project=project,
        rag_document_id="123",
    )
    api_client.force_login(project.owner)
    responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/documents/123",
        status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    caplog.set_level(logging.ERROR, logger="chat.views")

    url = f"/api/v1.0/projects/{project.pk}/attachments/{attachment.pk!s}/"
    response = api_client.delete(url)

    assert response.status_code == 204
    assert not models.ChatConversationAttachment.objects.filter(pk=attachment.pk).exists()
    assert any("Failed to delete RAG document 123" in record.message for record in caplog.records)


@responses.activate
def test_project_attachment_delete_removes_markdown_companion(api_client, albert_settings):
    """Deleting the original drops its hidden markdown companion row too.

    Non-text uploads produce a `text/markdown` companion at index time
    (`conversion_from = original.key`); the bulk filter in `perform_destroy`
    must remove it so it never outlives the original.
    """
    project = factories.ChatProjectFactory(collection_id="42")
    original = factories.ChatProjectAttachmentFactory(
        project=project,
        file_name="paper.pdf",
        content_type="application/pdf",
        rag_document_id="123",
    )
    companion = factories.ChatProjectAttachmentFactory(
        project=project,
        uploaded_by=original.uploaded_by,
        key=original.key,  # shared S3 blob
        file_name="paper.pdf.md",
        content_type="text/markdown",
        conversion_from=original.key,
    )
    unrelated = factories.ChatProjectAttachmentFactory(
        project=project,
        uploaded_by=original.uploaded_by,
        file_name="other.md",
        content_type="text/markdown",
        conversion_from=None,
    )
    responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/documents/123",
        status=http_status.HTTP_204_NO_CONTENT,
    )
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk}/attachments/{original.pk!s}/"
    response = api_client.delete(url)

    assert response.status_code == 204
    assert not models.ChatConversationAttachment.objects.filter(pk=original.pk).exists()
    assert not models.ChatConversationAttachment.objects.filter(pk=companion.pk).exists()
    # Unrelated attachments in the same project must remain intact.
    assert models.ChatConversationAttachment.objects.filter(pk=unrelated.pk).exists()


@responses.activate
def test_project_attachment_delete_runs_rag_before_s3(api_client, albert_settings):
    """`perform_destroy` must remove the RAG document before deleting the S3 blob.

    Order matters: an S3 delete that succeeds while the RAG entry remains
    leaves the model returning chunks for content the user can no longer
    retrieve. The view's contract is RAG -> S3 -> companion -> DB row.
    """
    project = factories.ChatProjectFactory(collection_id="42")
    attachment = factories.ChatProjectAttachmentFactory(
        project=project,
        rag_document_id="123",
    )
    api_client.force_login(project.owner)
    responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/documents/123",
        status=http_status.HTTP_204_NO_CONTENT,
    )

    call_order = []
    real_storage_delete = default_storage.delete

    def _record_storage_delete(name):
        call_order.append("s3")
        return real_storage_delete(name)

    real_backend_path = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend.delete_document"
    )
    with (
        mock.patch.object(default_storage, "delete", side_effect=_record_storage_delete),
        mock.patch(
            real_backend_path,
            side_effect=lambda *a, **kw: call_order.append("rag"),
        ),
    ):
        url = f"/api/v1.0/projects/{project.pk}/attachments/{attachment.pk!s}/"
        response = api_client.delete(url)

    assert response.status_code == 204
    assert call_order == ["rag", "s3"]


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

    response = api_client.post(url, {"file": file_obj, "file_name": "test.png"}, format="multipart")
    assert response.status_code == 404


@mock.patch("chat.views.attachments.malware_detection.analyse_file")
def test_project_backend_upload_success(mock_malware, api_client):
    """Test successful backend file upload for a project."""
    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(url, {"file": file_obj, "file_name": "test.png"}, format="multipart")

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


@mock.patch("chat.views.attachments.malware_detection.analyse_file")
def test_project_backend_upload_creates_s3_file(_mock_malware, api_client):
    """Test that backend upload creates file in S3."""
    project = factories.ChatProjectFactory()
    api_client.force_login(project.owner)

    url = f"/api/v1.0/projects/{project.pk!s}/attachments/backend-upload/"
    file_obj = BytesIO(PIXEL_PNG)
    file_obj.name = "test.png"

    response = api_client.post(url, {"file": file_obj, "file_name": "test.png"}, format="multipart")

    assert response.status_code == 201
    data = response.json()
    key = data["key"]

    assert default_storage.exists(key)

    with default_storage.open(key, "rb") as f:
        content = f.read()
    assert content == PIXEL_PNG


# ------------------------------------------------------------------ #
# Reindex (user-initiated retry of a failed indexing)
# ------------------------------------------------------------------ #


def test_project_attachment_reindex_not_owner_forbidden(api_client):
    """A user who does not own the project cannot reindex its attachments."""
    attachment = factories.ChatProjectAttachmentFactory(
        index_state=AttachmentIndexState.FAILED,
    )
    api_client.force_login(factories.UserFactory())

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/reindex/"
    response = api_client.post(url)

    assert response.status_code == 404


@mock.patch("chat.views.attachments.index_project_attachment_task")
def test_project_attachment_reindex_success(mock_task, api_client):
    """Reindexing a FAILED attachment resets it to INDEXING and re-enqueues the task."""
    attachment = factories.ChatProjectAttachmentFactory(
        content_type="application/pdf",
        upload_state=AttachmentStatus.READY,
        index_state=AttachmentIndexState.FAILED,
        processing_error="boom",
    )
    api_client.force_login(attachment.project.owner)

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/reindex/"
    response = api_client.post(url)

    assert response.status_code == 200
    attachment.refresh_from_db()
    assert attachment.index_state == AttachmentIndexState.INDEXING
    assert attachment.processing_error is None
    mock_task.delay.assert_called_once_with(attachment.pk)


@mock.patch("chat.views.attachments.index_project_attachment_task")
def test_project_attachment_reindex_rejected_when_not_failed(mock_task, api_client):
    """Reindex is only allowed for FAILED rows; an INDEXED row is rejected."""
    attachment = factories.ChatProjectAttachmentFactory(
        content_type="application/pdf",
        upload_state=AttachmentStatus.READY,
        index_state=AttachmentIndexState.INDEXED,
    )
    api_client.force_login(attachment.project.owner)

    url = f"/api/v1.0/projects/{attachment.project.pk}/attachments/{attachment.pk!s}/reindex/"
    response = api_client.post(url)

    assert response.status_code == 400
    attachment.refresh_from_db()
    assert attachment.index_state == AttachmentIndexState.INDEXED
    mock_task.delay.assert_not_called()
