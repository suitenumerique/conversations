"""Tests for the 0008 data migration: collection_id -> Collection model."""

import pytest
from django_test_migrations.migrator import Migrator

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = ("chat", "0007_collection_collectiondocument_and_more")
AFTER = ("chat", "0008_migrate_collection_id_to_collection")


@pytest.fixture()
def migrator(transactional_db):
    return Migrator(database="default")


def test_forward_creates_collection_from_collection_id(migrator):
    """Conversations with a collection_id get a Collection row."""
    old_state = migrator.apply_initial_migration(BEFORE)
    User = old_state.apps.get_model("core", "User")
    ChatConversation = old_state.apps.get_model("chat", "ChatConversation")

    user = User.objects.create(admin_email="test@example.com")
    conv = ChatConversation.objects.create(owner=user, collection_id="12345")

    new_state = migrator.apply_tested_migration(AFTER)
    Collection = new_state.apps.get_model("chat", "Collection")

    assert Collection.objects.count() == 1
    collection = Collection.objects.first()
    assert collection.backend == "albert"
    assert collection.external_id == "12345"
    assert collection.conversation_id == conv.pk
    assert collection.name == f"conversation-{conv.pk}"


def test_forward_skips_null_and_empty_collection_id(migrator):
    """Conversations without a collection_id are not migrated."""
    old_state = migrator.apply_initial_migration(BEFORE)
    User = old_state.apps.get_model("core", "User")
    ChatConversation = old_state.apps.get_model("chat", "ChatConversation")

    user = User.objects.create(admin_email="test-skip@example.com")
    ChatConversation.objects.create(owner=user, collection_id=None)
    ChatConversation.objects.create(owner=user, collection_id="")

    new_state = migrator.apply_tested_migration(AFTER)
    Collection = new_state.apps.get_model("chat", "Collection")

    assert Collection.objects.count() == 0


def test_backward_restores_collection_id(migrator):
    """Rolling back restores collection_id and removes Collection rows."""
    old_state = migrator.apply_initial_migration(BEFORE)
    User = old_state.apps.get_model("core", "User")
    ChatConversation = old_state.apps.get_model("chat", "ChatConversation")

    user = User.objects.create(admin_email="test-back@example.com")
    conv = ChatConversation.objects.create(owner=user, collection_id="99999")

    # Forward
    migrator.apply_tested_migration(AFTER)

    # Backward
    old_state = migrator.apply_tested_migration(BEFORE)
    ChatConversation = old_state.apps.get_model("chat", "ChatConversation")
    Collection = old_state.apps.get_model("chat", "Collection")

    conv.refresh_from_db()
    assert conv.collection_id == "99999"
    assert Collection.objects.count() == 0
