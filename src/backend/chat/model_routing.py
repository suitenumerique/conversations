"""Health-aware routing of new conversations to a healthy model.

When the default model is degraded (yellow/red), new conversations are pinned to
the first available fallback so the unhealthy main model is offloaded. An
explicit non-default ``model_hrid`` from the request is always respected (e.g.
dev/staging picker selections).
"""

from django.conf import settings

from chat.model_health import get_status_for_hrid, is_fallback_down
from chat.models import ModelHealth

_GREEN = ModelHealth.Status.GREEN


def resolve_effective_model_hrid(requested_hrid: str | None) -> str:
    """Return the HRID the next new conversation should use.

    An explicit request for any model *other than the default* is returned
    unchanged (this is the dev/staging picker path). An explicit request for
    the default model is equivalent to no request: the cascade still runs and
    routes around an unhealthy main. Otherwise the default model's cached
    health drives the cascade:
      - main green/unknown -> default
      - main degraded, fb1 available -> fb1
      - main degraded, fb1 down, fb2 available -> fb2
      - all down -> default (caller is expected to surface the outage banner)
    """
    default_hrid = settings.LLM_DEFAULT_MODEL_HRID

    if requested_hrid and requested_hrid != default_hrid:
        return requested_hrid

    main_status = get_status_for_hrid(default_hrid)
    if main_status in (None, _GREEN):
        return default_hrid

    for fb_hrid in (
        settings.LLM_FALLBACK_MODEL_HRID_1,
        settings.LLM_FALLBACK_MODEL_HRID_2,
    ):
        fb_status = get_status_for_hrid(fb_hrid)
        if not is_fallback_down(fb_hrid, fb_status):
            return fb_hrid

    return default_hrid
