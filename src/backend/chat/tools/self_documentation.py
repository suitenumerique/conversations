"""Self-documentation helpers and tool payload builder."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict
import re
import httpx
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

DOCS_HOST = "docs.numerique.gouv.fr"
SELF_DOCUMENTATION_ID = "e701bf5a-9c16-487e-b406-75767225fe3d"
#SELF_DOCUMENTATION_FILE = Path(__file__).resolve().parent.parent / "meta_docs" / "self_documentation.json"


#@lru_cache(maxsize=1)
async def load_static_self_documentation() -> Dict[str, Any]:
    """Load static self-documentation content from repository."""
    #with SELF_DOCUMENTATION_FILE.open(encoding="utf-8") as file:
    #    return json.load(file)

    url_transformed = f"https://{DOCS_HOST}/api/v1.0/documents/{SELF_DOCUMENTATION_ID}/content/?content_format=markdown"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(url_transformed)
            data = response.json()
            content = data.get('content', '')
            return content
    except Exception as e:
        logger.warning("Error fetching Docs content %s: %s", SELF_DOCUMENTATION_ID, e)
        return "There was an error fetching the self-documentation content."


async def build_self_documentation_payload(
    *,
    model_hrid: str,
    model_configuration: Any,
    web_search_feature_enabled: bool,
    smart_web_search_enabled: bool,
    document_upload_enabled: bool,
    web_search_runtime_enabled: bool,
) -> Dict[str, Any]:
    """Return a single payload combining static documentation and runtime details."""
    #static_doc = deepcopy(load_static_self_documentation())
    static_doc = await load_static_self_documentation()

    provider = getattr(model_configuration, "provider", None)
    provider_kind = getattr(provider, "kind", None)
    provider_hrid = getattr(provider, "hrid", None)

    runtime = {
        "model": {
            "hrid": model_hrid,
            "name": getattr(model_configuration, "model_name", None),
            "human_readable_name": getattr(model_configuration, "human_readable_name", None),
            "provider_kind": provider_kind,
            "provider_hrid": provider_hrid,
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
