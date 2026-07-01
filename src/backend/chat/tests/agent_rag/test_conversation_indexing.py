"""Unit tests for conversation attachment RAG indexing.

The happy path (text file → collection created, `index_state=INDEXED`, conversation
`index_state=INDEXED`) is covered by `test_tasks.py`; these focus on the
companion creation, the failure path, and skip rules specific to the conversation
indexer.
"""

import logging

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
import responses
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat import factories
from chat.agent_rag.indexing import index_conversation_attachment
from chat.enums import AttachmentIndexState, CollectionIndexState
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


@pytest.fixture(name="conversation_text_attachment")
def fixture_conversation_text_attachment():
    """Real conversation attachment with content stored in default_storage."""
    saved_name = default_storage.save("conv-rag-test.txt", ContentFile(b"Hello conversation"))
    attachment = factories.ChatConversationAttachmentFactory(
        key=saved_name,
        file_name="hello.txt",
        content_type="text/plain",
        upload_state=AttachmentStatus.READY,
    )
    yield attachment
    default_storage.delete(saved_name)


@responses.activate
def test_index_skips_attachment_without_conversation():
    """Project-scoped attachments are silently skipped by the conversation indexer."""
    attachment = factories.ChatProjectAttachmentFactory(content_type="text/plain")

    index_conversation_attachment(attachment)

    assert len(responses.calls) == 0


@responses.activate
def test_index_creates_collection_and_marks_conversation_indexed(conversation_text_attachment):
    """First indexable file creates the collection and marks the conversation INDEXED."""
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

    index_conversation_attachment(conversation_text_attachment)

    conversation_text_attachment.refresh_from_db()
    conversation_text_attachment.conversation.refresh_from_db()
    assert conversation_text_attachment.conversation.collection_id == "42"
    assert conversation_text_attachment.conversation.index_state == CollectionIndexState.INDEXED
    assert conversation_text_attachment.rag_document_id == "1"
    assert conversation_text_attachment.is_indexed is True
    assert conversation_text_attachment.index_state == AttachmentIndexState.INDEXED
    assert create_mock.call_count == 1
    assert documents_mock.call_count == 1


@responses.activate
def test_index_creates_markdown_companion_for_non_text_input():
    """Non-text inputs (e.g. PDF) get a hidden markdown companion attachment."""
    saved_name = default_storage.save("conv-rag-test.pdf", ContentFile(b"%PDF-1.4 fake bytes"))
    attachment = factories.ChatConversationAttachmentFactory(
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

        index_conversation_attachment(attachment)

        companion = ChatConversationAttachment.objects.get(
            conversation_id=attachment.conversation_id, conversion_from=attachment.key
        )
        assert companion.file_name == "paper.pdf.md"
        assert companion.content_type == "text/markdown"
        assert companion.key != attachment.key
        assert companion.key.endswith(".md")
        assert default_storage.exists(companion.key)
        assert companion.upload_state == AttachmentStatus.READY
    finally:
        default_storage.delete(saved_name)
        if companion is not None:
            default_storage.delete(companion.key)


@responses.activate
def test_index_swallows_backend_errors(conversation_text_attachment, caplog):
    """Backend failures are logged, recorded as FAILED, but never raised."""
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

    index_conversation_attachment(conversation_text_attachment)

    assert any(
        "Failed to index conversation attachment" in record.message for record in caplog.records
    )
    conversation_text_attachment.refresh_from_db()
    assert conversation_text_attachment.index_state == AttachmentIndexState.FAILED
    assert conversation_text_attachment.processing_error
    # File stays usable/downloadable despite the indexing failure.
    assert conversation_text_attachment.upload_state == AttachmentStatus.READY
