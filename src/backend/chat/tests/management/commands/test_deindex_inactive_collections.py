"""Tests for the deindex_inactive_collections management command."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from django.core.management import call_command
from django.utils import timezone

import pytest

from chat.enums import CollectionIndexState
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.models import ChatConversation


def _make_backend_mock(**delete_kwargs):
    """Return a backend class mock whose instances have an awaitable delete_collection."""
    mock_backend_cls = MagicMock()
    mock_backend_cls.return_value.delete_collection = AsyncMock(**delete_kwargs)
    return mock_backend_cls


@pytest.mark.django_db(transaction=True)
def test_deindexes_inactive_conversation(settings):
    """Active collection on inactive conversation is deleted and collection_id nulled."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id="albert-123")
    ChatConversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now() - timedelta(days=31)
    )

    mock_backend_cls = _make_backend_mock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    mock_backend_cls.assert_called_once_with(collection_id="albert-123")
    mock_backend_cls.return_value.delete_collection.assert_called_once()
    conversation.refresh_from_db()
    assert conversation.collection_id is None
    assert conversation.index_state == CollectionIndexState.DEINDEXED


@pytest.mark.django_db(transaction=True)
def test_skips_active_conversation(settings):
    """Collection on a recently active conversation is not deleted."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id="albert-456")
    # updated_at is auto_now so it is already recent — no override needed

    mock_backend_cls = _make_backend_mock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    mock_backend_cls.return_value.delete_collection.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.collection_id == "albert-456"


@pytest.mark.django_db(transaction=True)
def test_skips_conversation_without_collection(settings):
    """Conversation without a collection_id is never processed."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id=None)
    ChatConversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now() - timedelta(days=31)
    )

    mock_backend_cls = _make_backend_mock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    mock_backend_cls.assert_not_called()
    mock_backend_cls.return_value.delete_collection.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_continues_on_error(settings):
    """If the first conversation fails, the second one is still processed."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30

    conv1 = ChatConversationFactory(collection_id="albert-fail")
    conv2 = ChatConversationFactory(collection_id="albert-ok")
    past = timezone.now() - timedelta(days=31)
    ChatConversation.objects.filter(pk__in=[conv1.pk, conv2.pk]).update(updated_at=past)

    def _instance_side_effect(collection_id):
        m = MagicMock()
        if collection_id == "albert-fail":
            m.delete_collection.side_effect = RuntimeError("API error")
        return m

    mock_backend_cls = MagicMock(side_effect=_instance_side_effect)

    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    assert mock_backend_cls.call_count == 2

    conv1.refresh_from_db()
    conv2.refresh_from_db()
    # conv1 failed, collection_id should remain set
    assert conv1.collection_id == "albert-fail"
    # conv2 succeeded, collection_id should be None
    assert conv2.collection_id is None


@pytest.mark.django_db(transaction=True)
def test_rollback_restores_exact_pre_deindex_state(settings):
    """On delete_collection failure, conversation and attachment state are restored exactly."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    # Use ERROR (not INDEXED) to prove index_state is restored verbatim, not hardcoded.
    conv = ChatConversationFactory(
        collection_id="albert-fail", index_state=CollectionIndexState.ERROR
    )
    past = timezone.now() - timedelta(days=31)
    ChatConversation.objects.filter(pk=conv.pk).update(updated_at=past)
    # One indexed attachment and one not-yet-indexed attachment to cover both is_indexed values.
    att_indexed = ChatConversationAttachmentFactory(
        conversation=conv, is_indexed=True, rag_document_id="doc-abc"
    )
    att_pending = ChatConversationAttachmentFactory(
        conversation=conv, is_indexed=False, rag_document_id=None
    )

    mock_instance = MagicMock()
    mock_instance.delete_collection.side_effect = RuntimeError("API error")
    mock_backend_cls = MagicMock(return_value=mock_instance)
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    conv.refresh_from_db()
    assert conv.collection_id == "albert-fail"
    assert conv.index_state == CollectionIndexState.ERROR
    att_indexed.refresh_from_db()
    assert att_indexed.is_indexed is True
    assert att_indexed.rag_document_id == "doc-abc"
    att_pending.refresh_from_db()
    assert att_pending.is_indexed is False
    assert att_pending.rag_document_id is None


@pytest.mark.django_db(transaction=True)
def test_does_not_update_updated_at(settings):
    """Running the command must not change updated_at on the conversation."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id="albert-789")
    past = timezone.now() - timedelta(days=31)
    ChatConversation.objects.filter(pk=conversation.pk).update(updated_at=past)
    conversation.refresh_from_db()
    original_updated_at = conversation.updated_at

    mock_backend_cls = _make_backend_mock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    conversation.refresh_from_db()
    assert conversation.updated_at == original_updated_at
