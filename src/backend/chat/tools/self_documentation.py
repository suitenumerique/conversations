"""Self-documentation helpers and tool payload builder."""

import logging
from typing import Any, Dict

from django.conf import settings

from asgiref.sync import sync_to_async

from core.models import SiteConfiguration

logger = logging.getLogger(__name__)


async def load_db_self_documentation() -> str:
    """Load self documentation from DB. Returns empty string if not set"""
    get_solo = sync_to_async(SiteConfiguration.get_solo)
    self_doc = await get_solo()
    return self_doc.self_documentation or ""


async def build_self_documentation_payload(
    *, model_hrid: str, model_configuration: Any, tools_configuration: Dict[str, bool]
) -> Dict[str, Any]:
    """Return a single payload combining static documentation and runtime details."""
    static_doc = await load_db_self_documentation()

    provider = getattr(model_configuration, "provider", None)
    provider_kind = getattr(provider, "kind", None)
    provider_hrid = getattr(provider, "hrid", None)

    runtime = {
        "model": {
            "hrid": model_hrid,
            "name": getattr(model_configuration, "model_name", None),
            "human_readable_name": getattr(model_configuration, "human_readable_name", None),
            "max_tokens": getattr(
                getattr(model_configuration, "settings", None), "max_tokens", None
            ),
            "provider_kind": provider_kind,
            "provider_hrid": provider_hrid,
        },
        "tools": tools_configuration,
        "attachments": {
            "max_size_bytes": settings.ATTACHMENT_MAX_SIZE,
            "max_size_mb": round(settings.ATTACHMENT_MAX_SIZE / (1024 * 1024), 2),
            "unsafe_mime_type_check_enabled": settings.ATTACHMENT_CHECK_UNSAFE_MIME_TYPES_ENABLED,
            "unsafe_mime_types_blacklist": settings.ATTACHMENT_UNSAFE_MIME_TYPES,
        },
    }

    payload = {
        "self_documentation": static_doc,
        "runtime": runtime,
        "notes": {
            "priority_rule": "When static and runtime differ, runtime values are authoritative.",
            "scope": "This payload is intended for assistant self-description meta questions.",
        },
    }
    return payload
