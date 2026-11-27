"""core.0017: the data.gouv opt-in becomes the `datagouv` slug in `allowed_connectors`."""

import pytest

pytestmark = pytest.mark.django_db

BEFORE = ("core", "0016_normalize_stored_user_emails")
AFTER = ("core", "0017_user_allowed_connectors")


def _user(model, sub, **fields):
    """A user row, through the historical model of the migration state."""
    return model.objects.create(sub=sub, email=f"{sub}@example.org", **fields)


def test_a_data_gouv_opt_in_is_carried_over(migrator):
    """Existing users keep their consent, under the slug the declaration keeps."""
    old_state = migrator.apply_initial_migration(BEFORE)
    old_user = old_state.apps.get_model("core", "User")
    _user(old_user, "opted-in", allow_datagouv_connector=True)
    _user(old_user, "opted-out", allow_datagouv_connector=False)

    new_state = migrator.apply_tested_migration(AFTER)
    new_user = new_state.apps.get_model("core", "User")

    assert new_user.objects.get(sub="opted-in").allowed_connectors == ["datagouv"]
    assert new_user.objects.get(sub="opted-out").allowed_connectors == []
    assert "allow_datagouv_connector" not in {f.name for f in new_user._meta.get_fields()}


def test_the_migration_can_be_reversed(migrator):
    """Rolling back restores the data.gouv boolean; other connectors' opt-ins are lost."""
    new_state = migrator.apply_initial_migration(AFTER)
    new_user = new_state.apps.get_model("core", "User")
    _user(new_user, "both", allowed_connectors=["sofia", "datagouv"])
    _user(new_user, "other", allowed_connectors=["sofia"])

    old_state = migrator.apply_tested_migration(BEFORE)
    old_user = old_state.apps.get_model("core", "User")

    assert old_user.objects.get(sub="both").allow_datagouv_connector is True
    assert old_user.objects.get(sub="other").allow_datagouv_connector is False
