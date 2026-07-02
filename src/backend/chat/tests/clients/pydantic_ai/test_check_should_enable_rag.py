"""Unit tests for AIAgentService._check_should_enable_rag."""
# pylint: disable=protected-access

import pytest
from asgiref.sync import async_to_sync

from core.feature_flags.flags import FeatureToggle
from core.file_upload.enums import AttachmentStatus

from chat.clients.pydantic_ai import AIAgentService
from chat.enums import CollectionIndexState
from chat.factories import (
    ChatConversationAttachmentFactory,
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
)

pytestmark = pytest.mark.django_db


def _check(conversation, *, conversation_has_documents=False):
    service = AIAgentService(conversation, user=conversation.owner)
    return async_to_sync(service._check_should_enable_rag)(conversation_has_documents)


def test_returns_false_when_feature_disabled(feature_flags):
    """Feature flag short-circuits the check."""
    feature_flags.document_upload = FeatureToggle.DISABLED
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id="42",
    )

    assert _check(conversation, conversation_has_documents=False) is False
    assert _check(conversation, conversation_has_documents=True) is False


def test_returns_true_when_conversation_has_documents_arg():
    """Caller-provided in-message-document signal enables RAG once documents are indexed.

    In practice _parse_input_documents always runs before this check and sets
    index_state=INDEXED, so the conversation must reflect that post-parse state.
    """
    conversation = ChatConversationFactory(
        index_state=CollectionIndexState.INDEXED,
        collection_id="col-abc",
    )

    assert _check(conversation, conversation_has_documents=True) is True


def test_returns_false_with_no_attachments():
    """No documents anywhere → no RAG."""
    conversation = ChatConversationFactory()

    assert _check(conversation) is False


def test_returns_true_with_conversation_indexed_text_attachment():
    """A conversation attachment whose RAG round-trip succeeded
    (`rag_document_id` populated) enables RAG."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id="42",
    )

    assert _check(conversation) is True


def test_returns_false_when_text_attachment_is_not_indexed():
    """A READY text attachment without `rag_document_id` (RAG store call
    failed silently) must NOT enable RAG. The gate proxies actual indexed
    state, not just upload completion."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id=None,
    )

    assert _check(conversation) is False


def test_returns_false_with_conversation_ready_image_only():
    """Image-only attachments don't enable the RAG tool."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="image/png",
    )

    assert _check(conversation) is False


def test_returns_false_with_conversation_pending_attachment():
    """Non-READY attachments are ignored - they would be unsearchable."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.PENDING,
        content_type="text/plain",
    )

    assert _check(conversation) is False


def test_returns_false_for_companion_only():
    """A markdown conversion artifact alone shouldn't trip the gate.

    Companions never carry their own `rag_document_id` (the original carries
    it after indexing succeeds), so an orphan companion - or a companion
    without a successfully-indexed original - cannot trigger RAG enablement.
    """
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        conversion_from="some/original.pdf",
    )

    assert _check(conversation) is False


def test_returns_true_with_project_indexed_text_attachment():
    """An indexed project attachment enables RAG for any conversation in the project."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id="42",
    )

    assert _check(conversation) is True


def test_returns_false_with_project_ready_image_only():
    """Image-only project attachments don't enable the RAG tool."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="image/jpeg",
    )

    assert _check(conversation) is False


def test_returns_false_with_project_pending_attachment():
    """Non-READY project attachments are ignored."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.SUSPICIOUS,
        content_type="text/plain",
    )

    assert _check(conversation) is False


def test_project_attachment_does_not_leak_to_unlinked_conversation():
    """Indexed project attachments must not enable RAG on a conversation not in the project."""
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
        rag_document_id="42",
    )
    standalone_conversation = ChatConversationFactory(owner=project.owner)

    assert _check(standalone_conversation) is False


def test_returns_false_when_only_unindexed_pdf_in_project():
    """A non-text upload whose indexing did not finish (`rag_document_id`
    still NULL) must NOT enable RAG.

    Without this guard the gate fires on the original PDF and the model
    sees an empty/broken RAG context - it then asks summarize and gets
    `No text documents found`, telling the user the docs aren't there
    even though the row IS in the DB.
    """
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="application/pdf",
        rag_document_id=None,
    )

    assert _check(conversation) is False


def test_returns_true_when_indexed_pdf_in_project():
    """A PDF whose indexing succeeded (rag_document_id set) enables RAG.

    The companion row that the indexer creates alongside is irrelevant to
    the gate - only the original's rag_document_id matters.
    """
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    original = ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="application/pdf",
        rag_document_id="42",
    )
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        conversion_from=original.key,
    )

    assert _check(conversation) is True
