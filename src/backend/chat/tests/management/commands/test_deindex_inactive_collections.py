"""Tests for the deindex_inactive_collections management command."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.utils import timezone

import pytest

from chat.factories import ChatConversationFactory
from chat.models import ChatConversation


@pytest.mark.django_db()
def test_deindexes_inactive_conversation(settings):
    """Active collection on inactive conversation is deleted and collection_id nulled."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id="albert-123")
    ChatConversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now() - timedelta(days=31)
    )

    mock_backend_cls = MagicMock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    mock_backend_cls.assert_called_once_with(collection_id="albert-123")
    mock_backend_cls.return_value.delete_collection.assert_called_once()
    conversation.refresh_from_db()
    assert conversation.collection_id is None


@pytest.mark.django_db()
def test_skips_active_conversation(settings):
    """Collection on a recently active conversation is not deleted."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id="albert-456")
    # updated_at is auto_now so it is already recent — no override needed

    mock_backend_cls = MagicMock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    mock_backend_cls.return_value.delete_collection.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.collection_id == "albert-456"


@pytest.mark.django_db()
def test_skips_conversation_without_collection(settings):
    """Conversation without a collection_id is never processed."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id=None)
    ChatConversation.objects.filter(pk=conversation.pk).update(
        updated_at=timezone.now() - timedelta(days=31)
    )

    mock_backend_cls = MagicMock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    mock_backend_cls.assert_not_called()
    mock_backend_cls.return_value.delete_collection.assert_not_called()


@pytest.mark.django_db()
def test_continues_on_error(settings):
    """If the first conversation fails, the second one is still processed."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30

    conv1 = ChatConversationFactory(collection_id="albert-fail")
    conv2 = ChatConversationFactory(collection_id="albert-ok")
    past = timezone.now() - timedelta(days=31)
    ChatConversation.objects.filter(pk__in=[conv1.pk, conv2.pk]).update(updated_at=past)

    mock_backend_cls = MagicMock()
    # First call raises, second call succeeds
    mock_backend_cls.return_value.delete_collection.side_effect = [
        Exception("API error"),
        None,
    ]

    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    assert mock_backend_cls.return_value.delete_collection.call_count == 2

    conv1.refresh_from_db()
    conv2.refresh_from_db()
    # conv1 failed, collection_id should remain set
    assert conv1.collection_id == "albert-fail"
    # conv2 succeeded, collection_id should be None
    assert conv2.collection_id is None


@pytest.mark.django_db()
def test_does_not_update_updated_at(settings):
    """Running the command must not change updated_at on the conversation."""
    settings.RAG_COLLECTION_INACTIVITY_DAYS = 30
    conversation = ChatConversationFactory(collection_id="albert-789")
    past = timezone.now() - timedelta(days=31)
    ChatConversation.objects.filter(pk=conversation.pk).update(updated_at=past)
    conversation.refresh_from_db()
    original_updated_at = conversation.updated_at

    mock_backend_cls = MagicMock()
    with patch(
        "chat.management.commands.deindex_inactive_collections.import_string",
        return_value=mock_backend_cls,
    ):
        call_command("deindex_inactive_collections")

    conversation.refresh_from_db()
    assert conversation.updated_at == original_updated_at
