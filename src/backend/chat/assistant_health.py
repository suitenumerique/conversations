"""Helper that maps cached model health statuses to UI banners."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from core.models import SiteConfiguration

from chat.model_health import get_status_for_hrid, is_fallback_down
from chat.models import ModelHealth

_GREEN = ModelHealth.Status.GREEN
_YELLOW = ModelHealth.Status.YELLOW  # non-enabled: F401
_RED = ModelHealth.Status.RED

_BANNER_SLOW = {
    "level": "warning",
    "title": _("High traffic - slowdowns"),
    "content": _(
        "The Assistant IA service is currently experiencing high demand. "
        "The tool remains operational but may be slower, or you may "
        "experience delays between messages."
    ),
}
_BANNER_DEGRADED = {
    "level": "warning",
    "title": _("High traffic - degraded service"),
    "content": _(
        "The service is experiencing high demand, "
        "which is affecting service quality. "
        "Some features may be impacted. If you encounter an error, "
        "please try again "
        "once this error banner disappears."
    ),
}
_BANNER_UNAVAILABLE = {
    "level": "alert",
    "title": _("Service unavailable"),
    "content": _(
        "The service is currently unavailable due to excessive load. "
        "The team is working to restore the Assistant as quickly as possible."
    ),
}


def compute_assistant_health_banners() -> dict:
    """
    Compute banners to surface based on live model health.

    Returns {"banners": [...], "blocked": bool}.
    Each banner: {"level": str, "title": str, "content": str}.
    """
    main_status = get_status_for_hrid(settings.LLM_DEFAULT_MODEL_HRID)

    if main_status in (None, _GREEN):
        return {"banners": [], "blocked": False}

    fb1_hrid = settings.LLM_FALLBACK_MODEL_HRID_1
    fb2_hrid = settings.LLM_FALLBACK_MODEL_HRID_2
    fb1_status = get_status_for_hrid(fb1_hrid)
    fb2_status = get_status_for_hrid(fb2_hrid)

    if fb1_status == _GREEN:
        return {"banners": [dict(_BANNER_SLOW)], "blocked": False}

    all_down = is_fallback_down(fb1_hrid, fb1_status) and is_fallback_down(fb2_hrid, fb2_status)
    if main_status == _RED and all_down:
        if SiteConfiguration.get_solo().block_on_full_outage:
            return {"banners": [dict(_BANNER_UNAVAILABLE)], "blocked": True}
        return {"banners": [dict(_BANNER_DEGRADED)], "blocked": False}

    return {"banners": [dict(_BANNER_DEGRADED)], "blocked": False}
