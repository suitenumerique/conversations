"""Tests for the fetch_model_health management command."""

import logging
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

import pytest
import requests as requests_lib

from core.models import ModelHealthSettings

from chat.models import ModelHealth


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before/after each test to avoid key leakage between tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def albert_settings(settings):
    """Set common Albert API settings shared by all tests."""
    settings.ALBERT_HEALTH_URL = "https://albert.test.fr/health/models"
    settings.ALBERT_HEALTH_TIMEOUT = 10


def _make_mock_response(data):
    """Return a mock requests.Response with the given data payload."""
    mock = MagicMock()
    mock.json.return_value = {"data": data}
    mock.raise_for_status.return_value = None
    return mock


@pytest.mark.django_db
def test_fetch_model_health_inserts_rows_and_sets_cache(settings):
    """On success: one DB row per model + Redis key set, Bearer token sent."""
    settings.ALBERT_API_KEY = "test-api-key"

    payload = [
        {"id": "BAAI/bge-m3", "status": "green"},
        {"id": "mistral-medium-2508", "status": "red"},
    ]

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response(payload),
    ) as mock_get:
        call_command("fetch_model_health", "--provider", "albert")

    mock_get.assert_called_once_with(
        settings.ALBERT_HEALTH_URL,
        headers={"Authorization": "Bearer test-api-key"},
        timeout=settings.ALBERT_HEALTH_TIMEOUT,
    )
    assert ModelHealth.objects.count() == 2

    row = ModelHealth.objects.get(provider="albert", model_id="BAAI/bge-m3")
    assert row.status == "green"

    assert cache.get("model_health:albert:BAAI/bge-m3") == "green"
    assert cache.get("model_health:albert:mistral-medium-2508") == "red"


@pytest.mark.django_db
def test_fetch_model_health_no_api_key_sends_no_auth_header(settings):
    """When ALBERT_API_KEY is None, no Authorization header is sent."""
    settings.ALBERT_API_KEY = None

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response([]),
    ) as mock_get:
        call_command("fetch_model_health", "--provider", "albert")

    mock_get.assert_called_once_with(
        settings.ALBERT_HEALTH_URL,
        headers={},
        timeout=settings.ALBERT_HEALTH_TIMEOUT,
    )


@pytest.mark.django_db
def test_fetch_model_health_http_error_leaves_db_and_cache_untouched():
    """On HTTP error: no DB rows created, no cache writes, CommandError raised."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests_lib.HTTPError("500 Server Error")

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=mock_resp,
    ):
        with pytest.raises(CommandError):
            call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 0
    assert cache.get("model_health:albert:BAAI/bge-m3") is None


@pytest.mark.django_db
def test_fetch_model_health_timeout_raises_command_error():
    """On network timeout: CommandError raised, DB untouched."""
    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        side_effect=requests_lib.Timeout("timed out"),
    ):
        with pytest.raises(CommandError):
            call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 0


@pytest.mark.django_db
def test_fetch_model_health_unknown_provider_raises_immediately():
    """Unknown --provider value raises before any HTTP call.

    call_command() raises CommandError (not SystemExit) for invalid choices.
    """
    with patch("chat.management.commands.fetch_model_health.requests.get") as mock_get:
        with pytest.raises(CommandError):
            call_command("fetch_model_health", "--provider", "unknown-provider")

    mock_get.assert_not_called()


@pytest.mark.django_db
def test_skip_when_run_recently(settings):
    """last_run_at = now - 2min, interval=5 → skip, no HTTP call, no DB row."""
    settings.ALBERT_API_KEY = None

    cfg = ModelHealthSettings.get_solo()
    cfg.poll_interval_minutes = 5
    cfg.last_run_at = timezone.now() - timedelta(minutes=2)
    cfg.save()

    out = StringIO()
    with patch("chat.management.commands.fetch_model_health.requests.get") as mock_get:
        call_command("fetch_model_health", "--provider", "albert", stdout=out)

    mock_get.assert_not_called()
    assert ModelHealth.objects.count() == 0
    assert "Skipping" in out.getvalue()


@pytest.mark.django_db
def test_runs_when_interval_elapsed(settings):
    """last_run_at = now - 6min, interval=5 → fetch runs, last_run_at updated."""
    settings.ALBERT_API_KEY = None

    cfg = ModelHealthSettings.get_solo()
    cfg.poll_interval_minutes = 5
    cfg.last_run_at = timezone.now() - timedelta(minutes=6)
    cfg.save()
    old_last_run = cfg.last_run_at

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response([{"id": "model-a", "status": "green"}]),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1
    cfg.refresh_from_db()
    assert cfg.last_run_at > old_last_run


@pytest.mark.django_db
def test_runs_when_never_run(settings):
    """last_run_at = None → fetch runs regardless of interval."""
    settings.ALBERT_API_KEY = None

    cfg = ModelHealthSettings.get_solo()
    cfg.poll_interval_minutes = 5
    cfg.last_run_at = None
    cfg.save()

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response([{"id": "model-a", "status": "green"}]),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1
    cfg.refresh_from_db()
    assert cfg.last_run_at is not None


@pytest.mark.django_db
def test_no_new_row_if_status_unchanged(settings):
    """Same status on second run → still 1 row, updated_at advances."""
    settings.ALBERT_API_KEY = None

    payload = [{"id": "BAAI/bge-m3", "status": "green"}]

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response(payload),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1
    row_before = ModelHealth.objects.get(provider="albert", model_id="BAAI/bge-m3")
    updated_at_before = row_before.updated_at

    # Force interval to 0 so second run is not skipped
    cfg = ModelHealthSettings.get_solo()
    cfg.poll_interval_minutes = 0
    cfg.save()

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response(payload),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1
    row_after = ModelHealth.objects.get(provider="albert", model_id="BAAI/bge-m3")
    assert row_after.updated_at >= updated_at_before


@pytest.mark.django_db
def test_new_row_if_status_changed(settings):
    """Status changes green → red → 2 rows in DB."""
    settings.ALBERT_API_KEY = None

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response([{"id": "BAAI/bge-m3", "status": "green"}]),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1

    # Force interval to 0 so second run is not skipped
    cfg = ModelHealthSettings.get_solo()
    cfg.poll_interval_minutes = 0
    cfg.save()

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response([{"id": "BAAI/bge-m3", "status": "red"}]),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 2
    assert cache.get("model_health:albert:BAAI/bge-m3") == "red"


@pytest.mark.django_db
def test_last_run_at_set_before_http_call(settings):
    """last_run_at is persisted before the HTTP call to block concurrent re-entry."""
    settings.ALBERT_API_KEY = None

    last_run_at_during_request = []

    def capture_last_run_at(_url, **kwargs):
        last_run_at_during_request.append(ModelHealthSettings.objects.get().last_run_at)
        return _make_mock_response([])

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        side_effect=capture_last_run_at,
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert len(last_run_at_during_request) == 1
    assert last_run_at_during_request[0] is not None


@pytest.mark.django_db
def test_cache_invalidated_for_removed_models(settings):
    """Models absent from the API response have their cache keys deleted."""
    settings.ALBERT_API_KEY = None

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response(
            [{"id": "model-a", "status": "green"}, {"id": "model-b", "status": "green"}]
        ),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert cache.get("model_health:albert:model-a") == "green"
    assert cache.get("model_health:albert:model-b") == "green"

    cfg = ModelHealthSettings.get_solo()
    cfg.poll_interval_minutes = 0
    cfg.save()

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response([{"id": "model-a", "status": "green"}]),
    ):
        call_command("fetch_model_health", "--provider", "albert")

    assert cache.get("model_health:albert:model-a") == "green"
    assert cache.get("model_health:albert:model-b") is None


@pytest.mark.django_db
def test_unknown_status_skipped_with_warning(settings, caplog):
    """Items with unknown status values are skipped — no DB row, no cache write."""
    settings.ALBERT_API_KEY = None

    with patch(
        "chat.management.commands.fetch_model_health.requests.get",
        return_value=_make_mock_response(
            [{"id": "model-a", "status": "yellow"}, {"id": "model-b", "status": "green"}]
        ),
    ):
        with caplog.at_level(logging.WARNING):
            call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1
    assert ModelHealth.objects.get().model_id == "model-b"
    assert cache.get("model_health:albert:model-a") is None
    assert cache.get("model_health:albert:model-b") == "green"
    assert "yellow" in caplog.text
