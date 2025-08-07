"""Tests for feature flag models and enums."""

from typing import get_type_hints

import pytest
from pydantic import ValidationError

from core.feature_flags.flags import FeatureFlags, FeatureToggle


def test_is_always_enabled():
    """Test the is_always_enabled property."""
    assert FeatureToggle.ENABLED.is_always_enabled is True
    assert FeatureToggle.DYNAMIC.is_always_enabled is False
    assert FeatureToggle.DISABLED.is_always_enabled is False


def test_is_always_disabled():
    """Test the is_always_disabled property."""
    assert FeatureToggle.DISABLED.is_always_disabled is True
    assert FeatureToggle.DYNAMIC.is_always_disabled is False
    assert FeatureToggle.ENABLED.is_always_disabled is False


def test_defaults():
    """Ensure new instance has the declared defaults."""
    flags = FeatureFlags()
    assert flags.web_search is FeatureToggle.DISABLED
    assert flags.document_upload is FeatureToggle.DISABLED


@pytest.mark.parametrize(
    "field,value",
    [
        ("web_search", FeatureToggle.ENABLED),
        ("web_search", "enabled"),
    ],
)
def test_assign_valid_values(field, value):
    """Assignment via attribute or alias must accept valid values."""
    flags = FeatureFlags(**{field: value})
    assert flags.web_search == FeatureToggle(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("web_search", "not-a-state"),
        ("document_upload", 123),
        ("extra_field", "anything"),  # extra="forbid"
    ],
)
def test_reject_invalid_values(field, value):
    """Bad values or extra keys must raise ValidationError."""
    data = {field: value}
    with pytest.raises(ValidationError):
        FeatureFlags(**data)


def test_populate_by_name_and_alias():
    """Both snake_case and kebab-case aliases work."""
    from_snake = FeatureFlags(web_search="enabled")
    from_kebab = FeatureFlags(**{"web-search": "disabled"})
    assert from_snake.web_search is FeatureToggle.ENABLED
    assert from_kebab.web_search is FeatureToggle.DISABLED


def test_model_config_forbid_extra():
    """Extra keys are rejected."""
    with pytest.raises(ValidationError):
        FeatureFlags(unknown_flag="enabled")


def test_round_trip_serialization():
    """JSON round-trip keeps values intact."""
    original = FeatureFlags(
        web_search=FeatureToggle.DYNAMIC,
        document_upload=FeatureToggle.ENABLED,
    )

    raw = original.model_dump_json()
    restored = FeatureFlags.model_validate_json(raw)
    assert restored == original
    assert raw == ('{"web_search":"dynamic","document_upload":"enabled"}')

    raw_alias = original.model_dump_json(by_alias=True)
    restored_alias = FeatureFlags.model_validate_json(raw_alias)
    assert restored_alias == original
    assert raw_alias == ('{"web-search":"dynamic","document-upload":"enabled"}')


def test_all_fields_are_feature_toggle():
    """Static guarantee that every declared flag is a FeatureToggle."""
    hints = get_type_hints(FeatureFlags)
    for name, typ in hints.items():
        assert typ is FeatureToggle, f"{name} is not FeatureToggle"
