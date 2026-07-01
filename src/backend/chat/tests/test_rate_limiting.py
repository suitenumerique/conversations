"""Tests for the per-user token sliding window and cooldown heuristic."""

import types

from django.core.cache import cache

import pytest
from freezegun import freeze_time

from core.models import ChatCooldownSettings

from chat.llm_configuration import LLModel, LLMProvider
from chat.models import ModelHealth
from chat.rate_limiting import (
    ChatCooldownThrottle,
    compute_cooldown_seconds,
    get_cooldown_remaining,
    get_tokens_last_window,
    record_token_usage,
    set_cooldown,
)

pytestmark = pytest.mark.usefixtures("clear_cache")

# Trailing window the sliding-window tests run against (matches the singleton default).
_WINDOW = 20 * 60


def _model(*, cooldown_factor=None, provider_hrid="albert", with_provider=True):
    """Build a minimal LLModel for cooldown tests."""
    provider = (
        LLMProvider(hrid=provider_hrid, base_url="http://x", api_key="k") if with_provider else None
    )
    return LLModel(
        hrid="m",
        model_name="test-model",
        human_readable_name="M",
        provider_name=None if with_provider else "orphan",
        provider=provider,
        is_active=True,
        system_prompt="hi",
        tools=[],
        cooldown_factor=cooldown_factor,
    )


# --------------------------------------------------------------------------- #
# Sliding window
# --------------------------------------------------------------------------- #


def test_window_sums_usage_within_the_same_minute():
    """Multiple records in one minute accumulate in a single bucket."""
    with freeze_time("2026-06-09T10:00:00Z"):
        record_token_usage(1, 100, _WINDOW)
        record_token_usage(1, 200, _WINDOW)
        assert get_tokens_last_window(1, _WINDOW) == 300


def test_window_includes_usage_within_20_minutes():
    """Usage 19 minutes old is still counted."""
    with freeze_time("2026-06-09T10:00:00Z"):
        record_token_usage(1, 500, _WINDOW)
    with freeze_time("2026-06-09T10:19:00Z"):
        assert get_tokens_last_window(1, _WINDOW) == 500


def test_window_excludes_usage_older_than_20_minutes():
    """Usage 20 minutes old has rolled out of the window."""
    with freeze_time("2026-06-09T10:00:00Z"):
        record_token_usage(1, 500, _WINDOW)
    with freeze_time("2026-06-09T10:20:00Z"):
        assert get_tokens_last_window(1, _WINDOW) == 0


def test_window_is_isolated_per_user():
    """One user's usage does not bleed into another's window."""
    with freeze_time("2026-06-09T10:00:00Z"):
        record_token_usage(1, 100, _WINDOW)
        record_token_usage(2, 999, _WINDOW)
        assert get_tokens_last_window(1, _WINDOW) == 100


def test_record_ignores_non_positive_token_counts():
    """Zero/negative token counts are not recorded."""
    with freeze_time("2026-06-09T10:00:00Z"):
        record_token_usage(1, 0, _WINDOW)
        record_token_usage(1, -5, _WINDOW)
        assert get_tokens_last_window(1, _WINDOW) == 0


# --------------------------------------------------------------------------- #
# Cooldown heuristic
# --------------------------------------------------------------------------- #


def _cooldown(**overrides):
    """Deterministic cooldown parameters as an in-memory (unsaved) singleton."""
    return ChatCooldownSettings(
        **{"token_threshold": 1000, "default_factor": 0.5, "min_seconds": 10, **overrides}
    )


def _set_health(status, provider="albert", model_id="test-model"):
    cache.set(f"model_health:{provider}:{model_id}", status, timeout=None)


def test_no_cooldown_when_health_is_green():
    """Green health never incurs a cooldown, even far over threshold."""
    _set_health(ModelHealth.Status.GREEN)
    assert compute_cooldown_seconds(_model(), 100_000, _cooldown()) == 0


def test_no_cooldown_when_health_unknown():
    """Unknown health (no cached status) is treated as healthy -> no cooldown."""
    assert compute_cooldown_seconds(_model(), 1100, _cooldown()) == 0


def test_no_cooldown_when_not_healthy_but_under_threshold():
    """Degraded health under the threshold still incurs no cooldown."""
    _set_health(ModelHealth.Status.YELLOW)
    assert compute_cooldown_seconds(_model(), 1000, _cooldown()) == 0


def test_cooldown_when_yellow_and_over_threshold():
    """Yellow + over threshold: overage * factor + floor."""
    _set_health(ModelHealth.Status.YELLOW)
    # overage 100 * 0.5 + 10 floor = 60
    assert compute_cooldown_seconds(_model(), 1100, _cooldown()) == 60


def test_cooldown_when_red_and_over_threshold():
    """Red health over threshold also triggers a cooldown."""
    _set_health(ModelHealth.Status.RED)
    assert compute_cooldown_seconds(_model(), 1100, _cooldown()) == 60


def test_cooldown_uses_per_model_factor():
    """A model's own cooldown_factor overrides the default."""
    _set_health(ModelHealth.Status.YELLOW)
    # overage 100 * 2.0 + 10 floor = 210
    assert compute_cooldown_seconds(_model(cooldown_factor=2.0), 1100, _cooldown()) == 210


def test_no_cooldown_when_model_has_no_provider():
    """A model with no resolved provider cannot be health-checked -> no cooldown."""
    _set_health(ModelHealth.Status.YELLOW)
    assert compute_cooldown_seconds(_model(with_provider=False), 100_000, _cooldown()) == 0


# --------------------------------------------------------------------------- #
# Cooldown persistence + server-side throttle
# --------------------------------------------------------------------------- #


def _request(*, authenticated=True, pk=1):
    user = types.SimpleNamespace(is_authenticated=authenticated, pk=pk)
    return types.SimpleNamespace(user=user)


def test_set_and_get_cooldown_remaining():
    """A stored cooldown reports its remaining seconds."""
    with freeze_time("2026-06-09T10:00:00Z"):
        set_cooldown(1, 45)
        assert get_cooldown_remaining(1) == 45


def test_set_cooldown_ignores_non_positive():
    """A zero cooldown stores nothing."""
    with freeze_time("2026-06-09T10:00:00Z"):
        set_cooldown(1, 0)
        assert get_cooldown_remaining(1) == 0


def test_cooldown_expires_after_its_window():
    """The cooldown key disappears once its duration has elapsed."""
    with freeze_time("2026-06-09T10:00:00Z"):
        set_cooldown(1, 30)
    with freeze_time("2026-06-09T10:00:31Z"):
        assert get_cooldown_remaining(1) == 0


def test_throttle_allows_when_no_cooldown():
    """No active cooldown -> request allowed, no wait."""
    throttle = ChatCooldownThrottle()
    assert throttle.allow_request(_request(pk=7), None) is True
    assert throttle.wait() is None


def test_throttle_allows_anonymous_users():
    """Unauthenticated requests are not subject to the per-user cooldown."""
    throttle = ChatCooldownThrottle()
    assert throttle.allow_request(_request(authenticated=False), None) is True


def test_throttle_blocks_during_cooldown_and_reports_wait():
    """An active cooldown blocks the request and exposes the remaining wait."""
    with freeze_time("2026-06-09T10:00:00Z"):
        set_cooldown(7, 60)
        throttle = ChatCooldownThrottle()
        assert throttle.allow_request(_request(pk=7), None) is False
        assert throttle.wait() == 60
