"""Tests for feature flag helpers."""

import json
import logging
from unittest.mock import patch

import posthog
import pytest
import responses

from core.factories import UserFactory
from core.feature_flags.flags import FeatureToggle
from core.feature_flags.helpers import frontend_feature_name, is_feature_enabled

pytestmark = pytest.mark.django_db()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("web_search", "web-search"),
        ("document_upload", "document-upload"),
        ("SNAKE_CASE", "snake-case"),
        ("already-dashed", "already-dashed"),
    ],
)
def test_frontend_feature_name(raw: str, expected: str):
    """Test the feature name formatting function."""
    assert frontend_feature_name(raw) == expected


def test_is_feature_enabled_always_enabled(feature_flags):
    """Test that a feature that is always enabled returns True."""
    feature_flags.web_search = FeatureToggle.ENABLED
    feature_flags.document_upload = FeatureToggle.DISABLED
    user = UserFactory()
    assert is_feature_enabled(user, "web_search") is True


def test_is_feature_enabled_always_disabled(feature_flags):
    """Test that a feature that is always disabled returns False."""
    feature_flags.web_search = FeatureToggle.ENABLED
    feature_flags.document_upload = FeatureToggle.DISABLED
    user = UserFactory()
    assert is_feature_enabled(user, "document_upload") is False


@responses.activate
def test_is_feature_enabled_dynamic_posthog_true(feature_flags, settings):
    """Test that a dynamic feature returns the value from PostHog when PostHog is available."""
    settings.POSTHOG_KEY = {"id": "132456", "host": "https://eu.i.posthog-test.com"}

    posthog.api_key = settings.POSTHOG_KEY["id"]
    posthog.host = settings.POSTHOG_KEY["host"]

    responses.post(
        f"{posthog.host}/flags/?v=2", json={"flags": {"web-search": {"enabled": True}}}, status=200
    )

    feature_flags.web_search = FeatureToggle.DYNAMIC
    user = UserFactory()

    assert is_feature_enabled(user, "web_search") is True

    request_body = json.loads(responses.calls[0].request.body)
    assert request_body["distinct_id"] == str(user.pk)
    assert request_body["flag_keys_to_evaluate"] == ["web-search"]

    posthog.api_key = None
    posthog.host = None


@patch("core.feature_flags.helpers.posthog")
def test_is_feature_enabled_dynamic_posthog_false(mock_posthog, feature_flags):
    """Test that a dynamic feature returns the value from PostHog when PostHog is available."""
    feature_flags.web_search = FeatureToggle.DYNAMIC
    user = UserFactory()

    mock_posthog.feature_enabled.return_value = False
    assert is_feature_enabled(user, "web_search") is False


@patch("core.feature_flags.helpers.posthog", None)
def test_is_feature_enabled_dynamic_no_posthog(caplog, feature_flags):
    """Test that a dynamic feature falls back to settings when PostHog is not available."""
    caplog.set_level(logging.WARNING, logger="core")
    feature_flags.web_search = FeatureToggle.DYNAMIC

    user = UserFactory()

    assert is_feature_enabled(user, "web_search") is False

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert record.message == (
        "No feature flag manager found, cannot use dynamic for web_search -> disabled"
    )


def test_is_feature_enabled_missing_flag_raises_attribute_error():
    """Test that requesting an unknown feature flag raises an AttributeError."""
    user = UserFactory()

    with pytest.raises(AttributeError):
        is_feature_enabled(user, "unknown_feature")
