"""Helper that maps cached model health statuses to UI banners."""

from django.conf import settings
from django.utils.translation import gettext as _

from chat.model_health import get_model_health


def _get_status_for_hrid(hrid: str) -> str | None:
    """Return cached health status for an HRID, or None if unknown/uncached."""
    if not hrid:
        return None
    model = settings.LLM_CONFIGURATIONS.get(hrid)
    if model is None:
        return None
    if model.provider:
        return get_model_health(model.provider.hrid, model.model_name)
    # model_name in "provider:model_id" format when no explicit provider is configured
    parts = model.model_name.split(":", 1)
    if len(parts) == 2:
        return get_model_health(parts[0], parts[1])
    return None


def _fb_effective(fallback_hrids: list[str]) -> str | None:
    """
    Walk the fallback chain and return the status of the first non-red entry.

    Returns "red" if the chain is empty or every configured fallback is red.
    An empty chain (no fallbacks configured) intentionally returns "red" so
    that the caller shows banners based on the main model status alone —
    there is no fallback to absorb the degradation.
    """
    for hrid in fallback_hrids:
        if not hrid:
            continue
        status = _get_status_for_hrid(hrid)
        if status != "red":
            return status  # None, "green", or "orange" — all mean "not fully down"
    return "red"


def compute_assistant_health_banners() -> dict:
    """
    Compute banners to surface based on live model health.

    Returns {"banners": [...], "blocked": bool}.
    Each banner: {"level": str, "title": str, "content": ""}.
    """
    main_status = _get_status_for_hrid(settings.LLM_DEFAULT_MODEL_HRID)
    fb1 = getattr(settings, "LLM_FALLBACK_MODEL_HRID_1", "")
    fb2 = getattr(settings, "LLM_FALLBACK_MODEL_HRID_2", "")
    fb_eff = _fb_effective([fb1, fb2])

    if main_status in (None, "green"):
        return {"banners": [], "blocked": False}

    if main_status == "orange":
        if fb_eff in (None, "green"):
            return {"banners": [], "blocked": False}
        return {
            "banners": [
                {
                    "level": "warning",
                    "title": _("L'assistant répond lentement"),
                    "content": "",
                }
            ],
            "blocked": False,
        }

    # main_status == "red"
    if fb_eff in (None, "green"):
        return {"banners": [], "blocked": False}
    if fb_eff == "orange":
        return {
            "banners": [
                {
                    "level": "warning",
                    "title": _("L'assistant fonctionne en mode dégradé"),
                    "content": "",
                }
            ],
            "blocked": False,
        }
    # fb_eff == "red"
    return {
        "banners": [
            {
                "level": "alert",
                "title": _("Assistant indisponible"),
                "content": "",
            }
        ],
        "blocked": True,
    }
