"""Tests for maintenance mode (model, middleware, config endpoint)."""

import datetime

from django.test import override_settings
from django.utils import timezone

import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient

from core import models
from core.middleware import is_maintenance_active

pytestmark = pytest.mark.django_db


# ---------- Model.is_active_now() ----------


def test_maintenance_inactive_when_disabled():
    """A singleton with enabled=False is never active."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = False
    config.save()
    assert config.is_active_now() is False


def test_maintenance_active_when_enabled_no_bounds():
    """Enabled with null start/end bounds means always active."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = True
    config.save()
    assert config.is_active_now() is True


@freeze_time("2026-05-27 12:00:00")
def test_maintenance_inactive_when_starts_at_in_future():
    """Maintenance is hidden until starts_at is reached."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = True
    config.starts_at = timezone.now() + datetime.timedelta(hours=1)
    config.save()
    assert config.is_active_now() is False


@freeze_time("2026-05-27 12:00:00")
def test_maintenance_inactive_when_ends_at_in_past():
    """Maintenance auto-lifts once ends_at is in the past."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = True
    config.ends_at = timezone.now() - datetime.timedelta(hours=1)
    config.save()
    assert config.is_active_now() is False


@freeze_time("2026-05-27 12:00:00")
def test_maintenance_active_when_in_window():
    """Maintenance is active while now is within [starts_at, ends_at]."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = True
    config.starts_at = timezone.now() - datetime.timedelta(hours=1)
    config.ends_at = timezone.now() + datetime.timedelta(hours=1)
    config.save()
    assert config.is_active_now() is True


# ---------- is_maintenance_active() OR-precedence ----------


@override_settings(MAINTENANCE_MODE=True)
def test_env_var_forces_active_even_if_db_disabled():
    """The env-var escape hatch overrides the DB singleton."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = False
    config.save()
    assert is_maintenance_active() is True


@override_settings(MAINTENANCE_MODE=False)
def test_db_only_when_env_off():
    """With env off, the DB singleton state alone drives the flag."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = True
    config.save()
    assert is_maintenance_active() is True

    config.enabled = False
    config.save()
    assert is_maintenance_active() is False


# ---------- Middleware ----------


def _enable_maintenance():
    """Helper: flip the DB singleton on and return it."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = True
    config.save()
    return config


def test_middleware_blocks_api_endpoint():
    """Non-exempt API routes return 503 with the maintenance_mode code."""
    _enable_maintenance()
    client = APIClient()
    response = client.get("/api/v1.0/chat-conversations/")
    assert response.status_code == 503
    assert response.json() == {
        "code": "maintenance_mode",
        "detail": "Service under maintenance",
    }


def test_middleware_allows_config_endpoint():
    """The /config/ endpoint stays reachable and exposes the maintenance block."""
    _enable_maintenance()
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == 200
    assert response.json()["maintenance"] == {
        "enabled": True,
        "message": "",
        "ends_at": None,
    }


def test_middleware_allows_admin():
    """The /admin/ URL is always reachable so staff can toggle maintenance off."""
    _enable_maintenance()
    client = APIClient()
    response = client.get("/admin/")
    # Admin redirects unauthenticated users to login — both 200 and 302 prove the
    # middleware let it through (not 503).
    assert response.status_code != 503


def test_middleware_allows_heartbeats():
    """Kubernetes probes (heartbeat / lbheartbeat) must keep returning 200."""
    _enable_maintenance()
    client = APIClient()
    for path in ("/__heartbeat__", "/__lbheartbeat__"):
        response = client.get(path)
        assert response.status_code != 503, path


def test_middleware_passes_through_when_inactive():
    """With maintenance off, requests pass through and the maintenance block is null."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = False
    config.save()
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == 200
    assert response.json()["maintenance"] is None


@override_settings(MAINTENANCE_MODE=True)
def test_middleware_503_via_env_var_only():
    """Env var alone (DB disabled) still blocks."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = False
    config.save()
    client = APIClient()
    response = client.get("/api/v1.0/chat-conversations/")
    assert response.status_code == 503


@freeze_time("2026-05-27 12:00:00")
def test_middleware_includes_retry_after_when_ends_at_set():
    """When ends_at is known, the 503 response carries a Retry-After header."""
    config = models.MaintenanceMode.get_solo()
    config.enabled = True
    config.ends_at = timezone.now() + datetime.timedelta(seconds=600)
    config.save()
    client = APIClient()
    response = client.get("/api/v1.0/chat-conversations/")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "600"
