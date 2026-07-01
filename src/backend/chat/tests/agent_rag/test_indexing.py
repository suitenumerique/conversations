"""Unit tests for project attachment RAG indexing."""

import logging

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
import responses
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat import factories
from chat.agent_rag.indexing import index_project_attachment, is_indexable_for_rag
from chat.enums import AttachmentIndexState
from chat.models import ChatConversationAttachment

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure Albert backend + parser for the indexing tests."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.RAG_DOCUMENT_PARSER = "chat.agent_rag.document_converter.parser.AlbertParser"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


@pytest.fixture(name="project_text_attachment")
def fixture_project_text_attachment():
    """Real project attachment with content stored in default_storage.

    Marked READY so it is eligible for indexing - the malware safe-callback
    flips this state in production before invoking `index_project_attachment`.
    """
    saved_name = default_storage.save("project-rag-test.txt", ContentFile(b"Hello project content"))
    attachment = factories.ChatProjectAttachmentFactory(
        key=saved_name,
        file_name="hello.txt",
        content_type="text/plain",
        upload_state=AttachmentStatus.READY,
    )
    yield attachment
    default_storage.delete(saved_name)


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("text/plain", True),
        ("text/markdown", True),
        ("application/pdf", True),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", True),
        ("image/png", False),
        ("image/jpeg", False),
        ("image/webp", False),
    ],
)
def test_is_indexable_for_rag(content_type, expected):
    """Indexable for RAG covers every READY non-image content type."""
    attachment = factories.ChatProjectAttachmentFactory.build(
        content_type=content_type,
        upload_state=AttachmentStatus.READY,
    )
    assert is_indexable_for_rag(attachment) is expected


def test_is_indexable_for_rag_skips_pending_attachment():
    """A non-READY attachment is never indexable, regardless of content type."""
    attachment = factories.ChatProjectAttachmentFactory.build(
        content_type="text/plain",
        upload_state=AttachmentStatus.PENDING,
    )
    assert is_indexable_for_rag(attachment) is False


def test_is_indexable_for_rag_skips_companion_markdown():
    """The hidden markdown companion (`conversion_from` set) is not re-indexed."""
    attachment = factories.ChatProjectAttachmentFactory.build(
        content_type="text/markdown",
        upload_state=AttachmentStatus.READY,
        conversion_from="some/source.pdf",
    )
    assert is_indexable_for_rag(attachment) is False


@responses.activate
def test_index_skips_attachment_without_project():
    """Conversation-scoped attachments are silently skipped."""
    attachment = factories.ChatConversationAttachmentFactory(content_type="text/plain")

    index_project_attachment(attachment)

    assert len(responses.calls) == 0


@responses.activate
def test_index_skips_image_attachment(project_text_attachment):
    """Image attachments are skipped: no HTTP call, no collection created."""
    project_text_attachment.content_type = "image/png"
    project_text_attachment.save(update_fields=["content_type"])

    index_project_attachment(project_text_attachment)

    assert len(responses.calls) == 0
    project_text_attachment.project.refresh_from_db()
    assert project_text_attachment.project.collection_id is None


@responses.activate
def test_index_creates_collection_when_project_has_none(project_text_attachment):
    """First indexable file in a fresh project triggers collection creation."""
    create_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    documents_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 1},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    project_text_attachment.project.refresh_from_db()
    project_text_attachment.refresh_from_db()
    assert project_text_attachment.project.collection_id == "42"
    assert project_text_attachment.rag_document_id == "1"
    assert project_text_attachment.index_state == AttachmentIndexState.INDEXED
    assert project_text_attachment.processing_error is None
    assert create_mock.call_count == 1
    assert documents_mock.call_count == 1


@responses.activate
def test_index_reuses_existing_project_collection(project_text_attachment):
    """A project that already has a collection_id is not asked to create another."""
    project_text_attachment.project.collection_id = "999"
    project_text_attachment.project.save(update_fields=["collection_id"])

    create_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "should-not-be-called"},
        status=status.HTTP_200_OK,
    )
    documents_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 1},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    project_text_attachment.project.refresh_from_db()
    assert project_text_attachment.project.collection_id == "999"
    assert create_mock.call_count == 0
    assert documents_mock.call_count == 1


@responses.activate
def test_index_swallows_backend_errors(project_text_attachment, caplog):
    """Backend failures must be logged but never raised."""
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"error": "kaboom"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    caplog.set_level(logging.ERROR, logger="chat.agent_rag.indexing")

    index_project_attachment(project_text_attachment)

    assert any("Failed to index project attachment" in record.message for record in caplog.records)
    project_text_attachment.refresh_from_db()
    assert project_text_attachment.index_state == AttachmentIndexState.FAILED
    assert project_text_attachment.processing_error
    # File stays usable/downloadable despite the indexing failure.
    assert project_text_attachment.upload_state == AttachmentStatus.READY


@responses.activate
def test_index_is_idempotent_when_already_indexed(project_text_attachment):
    """An attachment that already carries a rag_document_id is not re-parsed."""
    project_text_attachment.rag_document_id = "777"
    project_text_attachment.save(update_fields=["rag_document_id"])

    create_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    documents_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 999},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    # No backend traffic; existing id is preserved.
    assert create_mock.call_count == 0
    assert documents_mock.call_count == 0
    project_text_attachment.refresh_from_db()
    assert project_text_attachment.rag_document_id == "777"
    # The idempotent path reconciles a lagging index_state to INDEXED.
    assert project_text_attachment.index_state == AttachmentIndexState.INDEXED


@responses.activate
def test_index_creates_markdown_companion_for_non_text_input():
    """Non-text inputs (e.g. PDF) get a hidden markdown companion attachment.

    The companion lives at a distinct S3 key (suffixed with `.md`) so the
    original binary stays intact for direct retrieval and works on storages
    without overwrite semantics. The parsed markdown is exposed for the
    system-prompt listing / summarize tools, mirroring the conversation
    indexing flow.
    """
    saved_name = default_storage.save("project-rag-test.pdf", ContentFile(b"%PDF-1.4 fake bytes"))
    attachment = factories.ChatProjectAttachmentFactory(
        key=saved_name,
        file_name="paper.pdf",
        content_type="application/pdf",
        upload_state=AttachmentStatus.READY,
    )
    companion = None
    try:
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/parse-beta",
            json={"data": [{"content": "# Parsed PDF\n\nbody"}]},
            status=status.HTTP_200_OK,
        )
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/collections",
            json={"id": "42"},
            status=status.HTTP_200_OK,
        )
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/documents",
            json={"id": 1},
            status=status.HTTP_201_CREATED,
        )

        index_project_attachment(attachment)

        companion = ChatConversationAttachment.objects.get(
            project_id=attachment.project_id, conversion_from=attachment.key
        )
        assert companion.file_name == "paper.pdf.md"
        assert companion.content_type == "text/markdown"
        # Companion lives at a distinct S3 key suffixed with `.md` so the
        # original binary stays intact and the row's key matches the actual
        # blob even on storages that do not overwrite same-name uploads.
        assert companion.key != attachment.key
        assert companion.key.endswith(".md")
        assert default_storage.exists(companion.key)
        assert companion.upload_state == AttachmentStatus.READY
    finally:
        default_storage.delete(saved_name)
        if companion is not None:
            default_storage.delete(companion.key)


@responses.activate
def test_index_does_not_create_companion_for_text_input(project_text_attachment):
    """A text/* input goes straight to the backend - no companion attachment."""
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 1},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    assert not ChatConversationAttachment.objects.filter(
        project_id=project_text_attachment.project_id,
        conversion_from=project_text_attachment.key,
    ).exists()
