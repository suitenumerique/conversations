"""Unit tests for project attachment RAG indexing."""

import io
import logging
import zipfile

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

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure Albert backend + parser for the indexing tests."""
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
def test_index_swallows_backend_errors(project_text_attachment, settings, caplog):
    """Backend failures must be logged but never raised."""
    settings.RAG_STORE_RETRY_DELAY_SECONDS = 0  # 500 triggers a retry; don't sleep
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
def test_index_fails_when_backend_returns_no_document_id(project_text_attachment):
    """A falsy document id must fail (FAILED), not leave the row stuck in INDEXING.

    The INDEXED transition and the idempotency guard both key off
    rag_document_id, so a missing id would otherwise wedge the row in INDEXING.
    """
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": ""},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    project_text_attachment.refresh_from_db()
    assert project_text_attachment.index_state == AttachmentIndexState.FAILED
    assert project_text_attachment.processing_error
    assert not project_text_attachment.rag_document_id
    assert project_text_attachment.upload_state == AttachmentStatus.READY


@responses.activate
def test_index_failure_captures_albert_response_body(project_text_attachment, settings, caplog):
    """A failed store logs and stores the Albert response body (the real reason),
    plus the file identity, instead of a generic exception string."""
    settings.RAG_STORE_RETRY_DELAY_SECONDS = 0  # don't actually sleep between retries
    project_text_attachment.project.collection_id = "999"
    project_text_attachment.project.save(update_fields=["collection_id"])

    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"detail": "model albert-large is overloaded"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    caplog.set_level(logging.ERROR, logger="chat.agent_rag.indexing")

    index_project_attachment(project_text_attachment)

    project_text_attachment.refresh_from_db()
    assert project_text_attachment.index_state == AttachmentIndexState.FAILED
    assert "HTTP 500" in project_text_attachment.processing_error
    assert "model albert-large is overloaded" in project_text_attachment.processing_error
    # The log line carries the file identity and the response body for triage.
    assert "hello.txt" in caplog.text
    assert "model albert-large is overloaded" in caplog.text


@responses.activate
def test_index_retries_once_on_transient_store_error(project_text_attachment, settings):
    """A transient 5xx on the store call is retried once, then succeeds."""
    settings.RAG_STORE_RETRY_DELAY_SECONDS = 0  # don't actually sleep in tests
    project_text_attachment.project.collection_id = "999"
    project_text_attachment.project.save(update_fields=["collection_id"])

    # responses returns registered mocks in order: first call 503, retry 201.
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"error": "flaky"},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 1},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    assert len(responses.calls) == 2  # initial attempt + one retry
    project_text_attachment.refresh_from_db()
    assert project_text_attachment.index_state == AttachmentIndexState.INDEXED
    assert project_text_attachment.rag_document_id == "1"
    assert project_text_attachment.processing_error is None


@responses.activate
def test_index_does_not_retry_on_client_error(project_text_attachment):
    """A 4xx store error is permanent for this input: no retry, straight to FAILED."""
    project_text_attachment.project.collection_id = "999"
    project_text_attachment.project.save(update_fields=["collection_id"])

    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"error": "bad request"},
        status=status.HTTP_400_BAD_REQUEST,
    )

    index_project_attachment(project_text_attachment)

    assert len(responses.calls) == 1  # no retry
    project_text_attachment.refresh_from_db()
    assert project_text_attachment.index_state == AttachmentIndexState.FAILED


@responses.activate
def test_index_does_not_retry_on_missing_document_id(project_text_attachment):
    """A 200 with no id means the chunks were stored; retrying would duplicate
    them, so it fails fast to FAILED instead of retrying."""
    project_text_attachment.project.collection_id = "999"
    project_text_attachment.project.save(update_fields=["collection_id"])

    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": ""},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    assert len(responses.calls) == 1  # no retry
    project_text_attachment.refresh_from_db()
    assert project_text_attachment.index_state == AttachmentIndexState.FAILED
    assert not project_text_attachment.rag_document_id


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


def test_index_reconcile_clears_stale_processing_error(project_text_attachment):
    """The idempotent reconcile clears an error left by a prior partial failure.

    A prior attempt can store the chunks (rag_document_id set) then fail on a
    later side-effect (e.g. companion S3 save), leaving the row FAILED with a
    processing_error. On retry the chunks already exist, so the row is genuinely
    indexed - it must land INDEXED with the stale error cleared.
    """
    project_text_attachment.rag_document_id = "777"
    project_text_attachment.index_state = AttachmentIndexState.FAILED
    project_text_attachment.processing_error = "companion S3 save failed"
    project_text_attachment.save(
        update_fields=["rag_document_id", "index_state", "processing_error"]
    )

    index_project_attachment(project_text_attachment)

    project_text_attachment.refresh_from_db()
    assert project_text_attachment.index_state == AttachmentIndexState.INDEXED
    assert project_text_attachment.is_indexed is True
    assert project_text_attachment.processing_error is None


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
def test_index_reconcile_rebuilds_missing_markdown_companion():
    """The idempotent reconcile re-writes a companion a prior run failed to store.

    A prior run stored the RAG chunks (rag_document_id set) then crashed before
    writing the markdown companion. On re-run the reconcile path re-parses (no
    re-store, so no /documents call and no duplicate chunks) and recreates the
    missing companion so summarize / the system-prompt listing work again.
    """
    saved_name = default_storage.save("project-rag-heal.pdf", ContentFile(b"%PDF-1.4 fake bytes"))
    attachment = factories.ChatProjectAttachmentFactory(
        key=saved_name,
        file_name="paper.pdf",
        content_type="application/pdf",
        upload_state=AttachmentStatus.READY,
        rag_document_id="already-stored",
    )
    companion = None
    try:
        parse_mock = responses.post(
            "https://albert.api.etalab.gouv.fr/v1/parse-beta",
            json={"data": [{"content": "# Parsed PDF\n\nbody"}]},
            status=status.HTTP_200_OK,
        )
        documents_mock = responses.post(
            "https://albert.api.etalab.gouv.fr/v1/documents",
            json={"id": 1},
            status=status.HTTP_201_CREATED,
        )

        index_project_attachment(attachment)

        # Re-parsed to recover the markdown, but never re-stored the chunks.
        assert parse_mock.call_count == 1
        assert documents_mock.call_count == 0
        companion = ChatConversationAttachment.objects.get(
            project_id=attachment.project_id, conversion_from=attachment.key
        )
        assert companion.file_name == "paper.pdf.md"
        assert companion.content_type == "text/markdown"
        assert companion.key.endswith(".md")
        assert default_storage.exists(companion.key)
    finally:
        default_storage.delete(saved_name)
        if companion is not None:
            default_storage.delete(companion.key)


@responses.activate
def test_index_reconcile_skips_companion_when_present(project_text_attachment):
    """Reconcile does no parse work when the companion already exists.

    A text input never has a companion, so the reconcile path must not re-parse
    it - the common idempotent re-run stays free of backend traffic.
    """
    project_text_attachment.rag_document_id = "already-stored"
    project_text_attachment.save(update_fields=["rag_document_id"])

    parse_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/parse-beta",
        json={"data": [{"content": "unused"}]},
        status=status.HTTP_200_OK,
    )

    index_project_attachment(project_text_attachment)

    assert parse_mock.call_count == 0


@responses.activate
def test_index_rejects_zip_bomb_and_marks_failed(settings):
    """A decompression-bomb project attachment is rejected before it is stored.

    The parser's `guard_zip_bomb` fires inside `parse_and_store_document`, so the
    document store HTTP call is never made; `index_project_attachment` catches the
    guard error and records a visible FAILED state while leaving the file usable.
    """
    settings.ATTACHMENT_PARSE_MAX_UNCOMPRESSED_SIZE = 1 * (2**20)  # 1MB

    # A DOCX (ZIP) declaring 4MB of zero-filled content: tiny compressed, well
    # over the 1MB uncompressed cap.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"\x00" * (4 * 2**20))
    saved_name = default_storage.save("project-bomb.docx", ContentFile(buffer.getvalue()))
    attachment = factories.ChatProjectAttachmentFactory(
        key=saved_name,
        file_name="bomb.docx",
        content_type=DOCX_CONTENT_TYPE,
        upload_state=AttachmentStatus.READY,
    )

    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    documents_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 1},
        status=status.HTTP_201_CREATED,
    )

    try:
        index_project_attachment(attachment)

        # Guard fired before the store: no document was persisted in the backend.
        assert documents_mock.call_count == 0
        attachment.refresh_from_db()
        assert attachment.index_state == AttachmentIndexState.FAILED
        assert attachment.processing_error
        assert not attachment.rag_document_id
        # File stays usable/downloadable despite the rejected indexing.
        assert attachment.upload_state == AttachmentStatus.READY
    finally:
        default_storage.delete(saved_name)


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
