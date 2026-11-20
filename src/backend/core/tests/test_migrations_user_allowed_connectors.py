"""
Tests for the migration turning the data.gouv opt-in into a list of connector slugs
"""

import pytest

pytestmark = pytest.mark.django_db

BEFORE = ("core", "0016_normalize_stored_user_emails")
AFTER = ("core", "0017_user_allowed_connectors")


def _user(user_model, sub, **fields):
    return user_model.objects.create(sub=sub, email=f"{sub}@example.com", **fields)


def test_migration_carries_the_datagouv_opt_in_over(migrator):
    """Users who opted in to data.gouv keep it, as its slug; the others start empty."""
    old_state = migrator.apply_initial_migration(BEFORE)
    old_user = old_state.apps.get_model("core", "User")
    _user(old_user, "opted-in", allow_datagouv_connector=True)
    _user(old_user, "opted-out", allow_datagouv_connector=False)

    new_state = migrator.apply_tested_migration(AFTER)
    new_user = new_state.apps.get_model("core", "User")

    assert new_user.objects.get(sub="opted-in").allowed_connectors == ["datagouv"]
    assert new_user.objects.get(sub="opted-out").allowed_connectors == []


def test_migration_reverts_to_the_boolean(migrator):
    """Rolling back restores the data.gouv opt-in from the slug."""
    new_state = migrator.apply_initial_migration(AFTER)
    new_user = new_state.apps.get_model("core", "User")
    _user(new_user, "opted-in", allowed_connectors=["legi", "datagouv"])
    _user(new_user, "other", allowed_connectors=["legi"])

    old_state = migrator.apply_tested_migration(BEFORE)
    old_user = old_state.apps.get_model("core", "User")

    assert old_user.objects.get(sub="opted-in").allow_datagouv_connector is True
    assert old_user.objects.get(sub="other").allow_datagouv_connector is False
