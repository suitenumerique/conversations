"""Tests for the fetch_model_health management command."""

import logging
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError

import pytest
import requests as requests_lib
import responses as responses_lib

from core.models import ModelHealthSettings

from chat.models import ModelHealth

# Matches the ALBERT_HEALTH_URL default in the Test settings class.
ALBERT_HEALTH_URL = "https://albert.api.etalab.gouv.fr/health/models"


@pytest.fixture(autouse=True)
def _clear_cache_between_tests(clear_cache):  # pylint: disable=unused-argument
    """Reset the cache shared by all tests."""


@pytest.mark.django_db
@responses_lib.activate
def test_fetch_model_health_inserts_rows_and_sets_cache():
    """On success: one DB row per model + Redis key set, Bearer token sent."""
    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={
            "data": [
                {"id": "BAAI/bge-m3", "status": "green"},
                {"id": "mistral-medium-2508", "status": "red"},
            ]
        },
    )

    call_command("fetch_model_health", "--provider", "albert")

    assert responses_lib.calls[0].request.headers["Authorization"] == "Bearer test-key"
    assert ModelHealth.objects.count() == 2
    row = ModelHealth.objects.get(provider="albert", model_id="BAAI/bge-m3")
    assert row.status == "green"
    assert cache.get("model_health:albert:BAAI/bge-m3") == "green"
    assert cache.get("model_health:albert:mistral-medium-2508") == "red"


@pytest.mark.django_db
@responses_lib.activate
def test_fetch_model_health_no_api_key_sends_no_auth_header(settings):
    """When ALBERT_API_KEY is None, no Authorization header is sent."""
    settings.ALBERT_API_KEY = None

    responses_lib.add(responses_lib.GET, ALBERT_HEALTH_URL, json={"data": []})

    call_command("fetch_model_health", "--provider", "albert")

    assert "Authorization" not in responses_lib.calls[0].request.headers


@pytest.mark.django_db
@responses_lib.activate
def test_fetch_model_health_http_error_leaves_db_and_cache_untouched():
    """On HTTP error: no DB rows created, no cache writes, CommandError raised."""
    responses_lib.add(responses_lib.GET, ALBERT_HEALTH_URL, status=500)

    with pytest.raises(CommandError):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 0
    assert cache.get("model_health:albert:BAAI/bge-m3") is None
    assert cache.get("model_health:poll_lock:albert") is None


@pytest.mark.django_db
@responses_lib.activate
def test_fetch_model_health_timeout_raises_command_error():
    """On network timeout: CommandError raised, DB untouched."""
    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        body=requests_lib.Timeout("timed out"),
    )

    with pytest.raises(CommandError):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 0


@pytest.mark.django_db
def test_fetch_model_health_unknown_provider_raises_immediately():
    """Unknown --provider value raises before any HTTP call.

    call_command() raises CommandError (not SystemExit) for invalid choices.
    """
    with pytest.raises(CommandError):
        call_command("fetch_model_health", "--provider", "unknown-provider")


@pytest.mark.django_db
def test_skip_when_lock_present():
    """Redis lock key already set → command skips, no HTTP call, no DB row."""
    cfg = ModelHealthSettings.get_solo()
    cfg.poll_interval_minutes = 5
    cfg.save()

    cache.set("model_health:poll_lock:albert", 1, timeout=300)

    out = StringIO()
    call_command("fetch_model_health", "--provider", "albert", stdout=out)

    assert ModelHealth.objects.count() == 0
    assert "Skipping" in out.getvalue()


@pytest.mark.django_db
@responses_lib.activate
def test_lock_acquired_on_run():
    """After a successful run, the Redis lock key is present."""
    responses_lib.add(responses_lib.GET, ALBERT_HEALTH_URL, json={"data": []})

    call_command("fetch_model_health", "--provider", "albert")

    assert cache.get("model_health:poll_lock:albert") is not None


@pytest.mark.django_db
@responses_lib.activate
def test_no_new_row_if_status_unchanged(settings):
    """Same status on second run → still 1 row (no new insert)."""
    settings.ALBERT_API_KEY = None

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={"data": [{"id": "BAAI/bge-m3", "status": "green"}]},
    )
    call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1

    cache.delete("model_health:poll_lock:albert")

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={"data": [{"id": "BAAI/bge-m3", "status": "green"}]},
    )
    call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1


@pytest.mark.django_db
@responses_lib.activate
def test_new_row_if_status_changed(settings):
    """Status changes green → red → 2 rows in DB."""
    settings.ALBERT_API_KEY = None

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={"data": [{"id": "BAAI/bge-m3", "status": "green"}]},
    )
    call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1

    cache.delete("model_health:poll_lock:albert")

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={"data": [{"id": "BAAI/bge-m3", "status": "red"}]},
    )
    call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 2
    assert cache.get("model_health:albert:BAAI/bge-m3") == "red"


@pytest.mark.django_db
@responses_lib.activate
def test_cache_invalidated_for_removed_models(settings):
    """Models absent from the API response have their cache keys deleted."""
    settings.ALBERT_API_KEY = None

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={"data": [{"id": "model-a", "status": "green"}, {"id": "model-b", "status": "green"}]},
    )
    call_command("fetch_model_health", "--provider", "albert")

    assert cache.get("model_health:albert:model-a") == "green"
    assert cache.get("model_health:albert:model-b") == "green"

    cache.delete("model_health:poll_lock:albert")

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={"data": [{"id": "model-a", "status": "green"}]},
    )
    call_command("fetch_model_health", "--provider", "albert")

    assert cache.get("model_health:albert:model-a") == "green"
    assert cache.get("model_health:albert:model-b") is None


@pytest.mark.django_db
@responses_lib.activate
def test_unknown_status_skipped_with_warning(settings, caplog):
    """Items with unknown status values are skipped — no DB row, no cache write."""
    settings.ALBERT_API_KEY = None

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={
            "data": [{"id": "model-a", "status": "purple"}, {"id": "model-b", "status": "green"}]
        },
    )

    with caplog.at_level(logging.WARNING):
        call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.count() == 1
    assert ModelHealth.objects.get().model_id == "model-b"
    assert cache.get("model_health:albert:model-a") is None
    assert cache.get("model_health:albert:model-b") == "green"
    assert "purple" in caplog.text


@pytest.mark.django_db
@responses_lib.activate
def test_legacy_orange_status_mapped_to_yellow(settings):
    """A provider still emitting the legacy 'orange' status is stored as 'yellow'."""
    settings.ALBERT_API_KEY = None

    responses_lib.add(
        responses_lib.GET,
        ALBERT_HEALTH_URL,
        json={"data": [{"id": "model-a", "status": "orange"}]},
    )

    call_command("fetch_model_health", "--provider", "albert")

    assert ModelHealth.objects.get(model_id="model-a").status == "yellow"
    assert cache.get("model_health:albert:model-a") == "yellow"
