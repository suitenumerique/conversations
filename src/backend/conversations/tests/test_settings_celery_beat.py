"""Tests for the CELERY_BEAT_SCHEDULE property and crontab_from_string helper."""

import pytest
from celery.schedules import crontab

from conversations.celery_settings import MODEL_HEALTH_POLL_PROVIDERS, crontab_from_string
from conversations.settings import Base


def test_default_beat_schedule_only_purges_tabular_results():
    """By default only the purge of unread tabular results runs, every hour."""
    schedule = Base().CELERY_BEAT_SCHEDULE

    assert list(schedule) == ["purge-tabular-results"]
    entry = schedule["purge-tabular-results"]
    assert entry["task"] == "chat.tasks.purge_tabular_results_task"
    assert entry["schedule"] == crontab(minute="23")


def test_tabular_results_purge_can_be_disabled():
    """An empty TABULAR_RESULTS_PURGE_CRON leaves the schedule empty."""

    class TestSettings(Base):
        """Fake test settings with every periodic task off."""

        TABULAR_RESULTS_PURGE_CRON = ""

    assert not TestSettings().CELERY_BEAT_SCHEDULE


def test_model_health_poll_entry():
    """MODEL_HEALTH_POLL_PROVIDER set builds one interval-based schedule entry."""

    class TestSettings(Base):
        """Fake test settings with model-health polling enabled."""

        MODEL_HEALTH_POLL_PROVIDER = "albert"
        MODEL_HEALTH_POLL_INTERVAL_SECONDS = 30
        TABULAR_RESULTS_PURGE_CRON = ""

    schedule = TestSettings().CELERY_BEAT_SCHEDULE

    assert list(schedule) == ["fetch-model-health"]
    entry = schedule["fetch-model-health"]
    assert entry["task"] == "chat.tasks.fetch_model_health_task"
    assert entry["schedule"] == 30
    assert entry["args"] == ("albert",)
    assert entry["options"] == {"expires": 30}


def test_deindex_entry_maps_cron_fields_to_crontab_kwargs():
    """DEINDEX_INACTIVE_COLLECTIONS_CRON set builds one crontab-based schedule entry."""

    class TestSettings(Base):
        """Fake test settings with de-index cron scheduling enabled."""

        DEINDEX_INACTIVE_COLLECTIONS_CRON = "0 3 1 6 *"
        TABULAR_RESULTS_PURGE_CRON = ""

    schedule = TestSettings().CELERY_BEAT_SCHEDULE

    assert list(schedule) == ["deindex-inactive-collections"]
    entry = schedule["deindex-inactive-collections"]
    assert entry["task"] == "chat.tasks.deindex_inactive_collections_task"
    assert entry["schedule"] == crontab(minute="0", hour="3", day_of_month="1", month_of_year="6")


def test_both_settings_produce_two_entries():
    """Both periodic settings set together build a schedule with both entries."""

    class TestSettings(Base):
        """Fake test settings with both periodic tasks enabled."""

        MODEL_HEALTH_POLL_PROVIDER = "albert"
        DEINDEX_INACTIVE_COLLECTIONS_CRON = "0 2 * * *"
        TABULAR_RESULTS_PURGE_CRON = ""

    schedule = TestSettings().CELERY_BEAT_SCHEDULE

    assert set(schedule) == {"fetch-model-health", "deindex-inactive-collections"}


def test_crontab_from_string_rejects_wrong_field_count():
    """A cron string without five fields raises ValueError."""
    with pytest.raises(ValueError, match="^SOME_CRON must have five"):
        crontab_from_string("0 2 * *", "SOME_CRON")

    with pytest.raises(ValueError):
        crontab_from_string("0 2 * * * *", "SOME_CRON")


def test_deindex_property_propagates_crontab_from_string_error():
    """A bad DEINDEX_INACTIVE_COLLECTIONS_CRON raises ValueError from the property."""

    class TestSettings(Base):
        """Fake test settings with a malformed de-index cron string."""

        DEINDEX_INACTIVE_COLLECTIONS_CRON = "0 2 * *"

    with pytest.raises(ValueError, match="^DEINDEX_INACTIVE_COLLECTIONS_CRON must"):
        _ = TestSettings().CELERY_BEAT_SCHEDULE


def test_purge_property_names_its_own_setting_in_crontab_error():
    """A bad TABULAR_RESULTS_PURGE_CRON is reported under its own name."""

    class TestSettings(Base):
        """Fake test settings with a malformed purge cron string."""

        TABULAR_RESULTS_PURGE_CRON = "23 * *"

    with pytest.raises(ValueError, match="^TABULAR_RESULTS_PURGE_CRON must"):
        _ = TestSettings().CELERY_BEAT_SCHEDULE


def test_model_health_poll_rejects_zero_interval():
    """A poll interval below 1 second raises ValueError from the property."""

    class TestSettings(Base):
        """Fake test settings with a zero model-health poll interval."""

        MODEL_HEALTH_POLL_PROVIDER = "albert"
        MODEL_HEALTH_POLL_INTERVAL_SECONDS = 0

    with pytest.raises(ValueError):
        _ = TestSettings().CELERY_BEAT_SCHEDULE


def test_model_health_poll_rejects_unknown_provider():
    """A provider not in MODEL_HEALTH_POLL_PROVIDERS raises ValueError from the property."""

    class TestSettings(Base):
        """Fake test settings with an unknown model-health provider."""

        MODEL_HEALTH_POLL_PROVIDER = "not-a-real-provider"

    with pytest.raises(ValueError):
        _ = TestSettings().CELERY_BEAT_SCHEDULE


def test_model_health_poll_providers_matches_command_providers():
    """MODEL_HEALTH_POLL_PROVIDERS must not drift from the command's own PROVIDERS."""
    # pylint: disable-next=import-outside-toplevel
    from chat.management.commands import fetch_model_health  # noqa: PLC0415

    assert set(MODEL_HEALTH_POLL_PROVIDERS) == set(fetch_model_health.PROVIDERS)
