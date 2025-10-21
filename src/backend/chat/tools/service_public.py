"""Service Public RAG search tool using Albert API pre-defined collections.

This tool reuses the existing Albert API RAG by directly querying the search
endpoint with a fixed set of curated collections (e.g. Service-Public, Travail-Emploi).
"""

from typing import List
import json
import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from pydantic_ai import RunContext, RunUsage
from pydantic_ai.messages import ToolReturn


logger = logging.getLogger(__name__)


# Default curated collections (Albert IDs)
DEFAULT_COLLECTION_IDS: List[int] = [784, 785]  # travail-emploi, service-public
PROMPT_PREFIX = "Voilà les informations trouvées, résume les pour répondre à la question de l'utilisateur, à la fin de ta réponse, ajoutes une section sources avec les urls des sources si présentes: "


def _albert_search_with_collections(query: str, collections: List[int]) -> dict:
    """Call Albert search with explicit collections.

    Returns a dict compatible with existing RAG result mapping tooling.
    """
    base_url = settings.ALBERT_API_URL
    api_key = settings.ALBERT_API_KEY
    endpoint = urljoin(base_url, "v1/search")

    # Minimal payload aligned with Albert API
    payload = {
        "collections": collections,
        "prompt": query,
        # Reasonable defaults; can be made configurable later if needed
        "k": getattr(settings, "RAG_WEB_SEARCH_CHUNK_NUMBER", 10),
        "web_search": False,
    }
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(endpoint, headers=headers, json=payload, timeout=settings.ALBERT_API_TIMEOUT)
    response.raise_for_status()
    return response.json()


async def service_public(ctx: RunContext, query: str) -> ToolReturn:
    """Search curated Service-Public collections on Albert and return snippets.

    Args:
        ctx: Run context (usage metering is updated here)
        query: The user query to search within curated collections
    """
    try:
        json_response = _albert_search_with_collections(query, DEFAULT_COLLECTION_IDS)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Albert Service Public search failed: %s", exc)
        return ToolReturn(return_value=[], content="", metadata={"error": str(exc)})

    # Map to a compact structure that the model can consume easily
    data = json_response.get("data", [])
    usage_obj = json_response.get("usage", {})

    compact = []
    sources = []
    for item in data:
        # Albert returns an object with fields: score, chunk{ content, metadata{ document_name } }
        chunk = item.get("chunk", {})
        metadata = chunk.get("metadata", {})
        compact.append(
            {
                "title": metadata.get("document_name"),
                "snippet": chunk.get("content"),
                "url": metadata.get("url"),
            }
        )
        if metadata.get("document_name"):
            sources.append(metadata["document_name"])

    # Update run usage if available
    if usage_obj:
        try:
            ctx.usage += RunUsage(
                input_tokens=usage_obj.get("prompt_tokens", 0),
                output_tokens=usage_obj.get("completion_tokens", 0),
            )
        except Exception:  # noqa: BLE001
            # Non-blocking if shape changes
            pass

    return ToolReturn(
        return_value=compact,
        content="",  # let the model consume return_value; avoid injecting in UI
        metadata={"sources": sources},
    )

