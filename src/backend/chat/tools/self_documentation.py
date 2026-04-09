"""Self-documentation helpers and tool payload builder."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from django.conf import settings


SELF_DOCUMENTATION_FILE = Path(__file__).resolve().parent.parent / "meta_docs" / "self_documentation.json"


@lru_cache(maxsize=1)
def load_static_self_documentation() -> Dict[str, Any]:
    """Load static self-documentation content from repository."""
    with SELF_DOCUMENTATION_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def build_self_documentation_payload(
    *,
    model_hrid: str,
    model_configuration: Any,
    web_search_feature_enabled: bool,
    smart_web_search_enabled: bool,
    document_upload_enabled: bool,
    web_search_runtime_enabled: bool,
) -> Dict[str, Any]:
    """Return a single payload combining static documentation and runtime details."""
    static_doc = deepcopy(load_static_self_documentation())

    provider = getattr(model_configuration, "provider", None)
    provider_kind = getattr(provider, "kind", None)
    provider_hrid = getattr(provider, "hrid", None)
    model_settings = getattr(model_configuration, "settings", None)
    max_tokens = getattr(model_settings, "max_tokens", None) if model_settings else None

    runtime = {
        "model": {
            "hrid": model_hrid,
            "name": getattr(model_configuration, "model_name", None),
            "human_readable_name": getattr(model_configuration, "human_readable_name", None),
            "provider_kind": provider_kind,
            "provider_hrid": provider_hrid,
            "max_tokens": max_tokens,
        },
        "features": {
            "document_upload_enabled": document_upload_enabled,
            "web_search_feature_enabled": web_search_feature_enabled,
            "smart_web_search_enabled": smart_web_search_enabled,
            "web_search_runtime_enabled": web_search_runtime_enabled,
            "internet_access_realtime": web_search_runtime_enabled,
        },
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
