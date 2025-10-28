"""Tooling around feature flags"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

try:
    import posthog
except ImportError:
    posthog = None

logger = logging.getLogger(__name__)


def frontend_feature_name(feature_name: str) -> str:
    """
    Formats the feature flag name to match the expected format in settings.
    This is the reverse of format_feature_flag_name_back.
    """
    return feature_name.lower().replace("_", "-")


def is_feature_enabled(
    user: User,
    feature_name: str,
) -> bool:
    """Whether a feature is enabled or not."""
    _settings_value = getattr(settings.FEATURE_FLAGS, feature_name)  # might raise on purpose
    if _settings_value.is_always_enabled:
        return True
    if _settings_value.is_always_disabled:
        return False

    # Then it's dynamic
    if posthog is not None:
        return posthog.feature_enabled(
            frontend_feature_name(feature_name),
            str(user.pk),  # same as set by the frontend
        )

    # No feature flag manager
    logger.warning(
        "No feature flag manager found, cannot use dynamic for %s -> disabled",
        feature_name,
    )
    return False
