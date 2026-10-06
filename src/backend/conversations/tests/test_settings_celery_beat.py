"""Tests for the CELERY_BEAT_SCHEDULE property and crontab_from_string helper."""

import pytest
from celery.schedules import crontab

from conversations.celery_settings import MODEL_HEALTH_POLL_PROVIDERS, crontab_from_string
from conversations.settings import Base


def test_default_beat_schedule_is_empty():
    """Both periodic settings default to off, so the schedule has no entries."""
    assert not Base().CELERY_BEAT_SCHEDULE


def test_model_health_poll_entry():
    """MODEL_HEALTH_POLL_PROVIDER set builds one interval-based schedule entry."""

    class TestSettings(Base):
        """Fake test settings with model-health polling enabled."""

        MODEL_HEALTH_POLL_PROVIDER = "albert"
        MODEL_HEALTH_POLL_INTERVAL_SECONDS = 30

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

    schedule = TestSettings().CELERY_BEAT_SCHEDULE

    assert set(schedule) == {"fetch-model-health", "deindex-inactive-collections"}


def test_arena_purge_entry_maps_cron_fields_to_crontab_kwargs():
    """ARENA_PURGE_CONTENT_CRON set builds one crontab-based schedule entry."""

    class TestSettings(Base):
        """Fake test settings with the Arena retention purge enabled."""

        ARENA_PURGE_CONTENT_CRON = "0 3 * * *"

    schedule = TestSettings().CELERY_BEAT_SCHEDULE

    assert list(schedule) == ["purge-arena-content"]
    entry = schedule["purge-arena-content"]
    assert entry["task"] == "chat.tasks.purge_arena_content_task"
    assert entry["schedule"] == crontab(minute="0", hour="3")


def test_arena_purge_property_rejects_bad_cron():
    """A bad ARENA_PURGE_CONTENT_CRON raises ValueError naming that setting."""

    class TestSettings(Base):
        """Fake test settings with a malformed Arena purge cron string."""

        ARENA_PURGE_CONTENT_CRON = "0 3 * *"

    with pytest.raises(ValueError, match="ARENA_PURGE_CONTENT_CRON"):
        _ = TestSettings().CELERY_BEAT_SCHEDULE


def test_crontab_from_string_rejects_wrong_field_count():
    """A cron string without five fields raises ValueError."""
    with pytest.raises(ValueError):
        crontab_from_string("0 2 * *")

    with pytest.raises(ValueError):
        crontab_from_string("0 2 * * * *")


def test_deindex_property_propagates_crontab_from_string_error():
    """A bad DEINDEX_INACTIVE_COLLECTIONS_CRON raises ValueError from the property."""

    class TestSettings(Base):
        """Fake test settings with a malformed de-index cron string."""

        DEINDEX_INACTIVE_COLLECTIONS_CRON = "0 2 * *"

    with pytest.raises(ValueError):
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
