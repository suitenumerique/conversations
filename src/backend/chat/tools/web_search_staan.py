"""Web juridique tool for the chat agent."""

import json
import logging

from django.conf import settings

import requests
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail

logger = logging.getLogger(__name__)

STAAN_MARKETS = frozenset({"fr-fr", "en-us", "de-de"})
STAAN_DEFAULT_MARKET = "en-us"

_STAAN_MARKET_BY_LANGUAGE_PREFIX = {
    "fr": "fr-fr",
    "en": "en-us",
    "de": "de-de",
}


def resolve_staan_market(language: str | None) -> str:
    """Map a UI language code to a supported Staan search market."""
    user_lang = (language or settings.LANGUAGE_CODE or "").lower()
    if user_lang in STAAN_MARKETS:
        return user_lang
    prefix = user_lang.split("-")[0] if user_lang else ""
    if prefix in _STAAN_MARKET_BY_LANGUAGE_PREFIX:
        return _STAAN_MARKET_BY_LANGUAGE_PREFIX[prefix]
    return STAAN_DEFAULT_MARKET


def _resolve_staan_market(ctx: RunContext) -> str:
    """Resolve the Staan market from the conversation context language."""
    return resolve_staan_market(getattr(ctx.deps, "language", None))


def staan_search(query: str, market: str) -> requests.Response:
    """
    Performs a search using the Staan API.

    Args:
        query: User query string.
        market: Staan search market (e.g. fr-fr, en-us, de-de).

    Returns:
        requests.Response: Raw HTTP response from the Staan API.

    """
    if not settings.STAAN_API_KEY:
        raise ValueError("Clé API Staan manquante (variable d'env STAAN_API_KEY)")

    params = {
        "q": query,
        "market": market,
        "extra_snippets": "true" if settings.STAAN_SEARCH_EXTRA_SNIPPETS else "false",
    }

    headers = {
        "Authorization": f"Bearer {settings.STAAN_API_KEY}",
    }

    response = requests.get(
        settings.STAAN_SEARCH_ENDPOINT,
        params=params,
        headers=headers,
        timeout=settings.STAAN_API_TIMEOUT,
    )
    response.raise_for_status()
    return response


def _collect_extra_snippets(
    result: dict,
    *,
    max_len_snippet: int,
    min_score: float,
) -> list[str]:
    """Extract extra snippet chunks from a Staan result, filtering by score and length."""
    raw_snippets = result.get("extra_snippets") or []
    if not raw_snippets:
        return []

    extra_snippets: list[str] = []
    for item in raw_snippets:
        if isinstance(item, dict):
            chunk = item.get("chunk", "")
            score = float(item.get("score", 0))
        else:
            chunk = str(item)
            score = min_score

        if score < min_score:
            continue

        current_length = len(" ".join(extra_snippets))
        if current_length + len(chunk) >= max_len_snippet:
            break
        extra_snippets.append(chunk)

    return extra_snippets


def format_staan(
    response: requests.Response,
    n_results: int | None = None,
    max_len_snippet: int | None = None,
    min_score: float | None = None,
) -> str:
    """
    Format a Staan API response to extract web results with snippets.

    Works whether or not ``extra_snippets`` was requested from the API:
    - without: uses the main ``snippet`` field only
    - with: adds filtered ``extra_snippets`` chunks (dict items with ``chunk`` / ``score``)

    Args:
        response: requests.Response object from Staan API
        n_results: Maximum number of web results to include
        max_len_snippet: Maximum total length of concatenated extra snippets per result
        min_score: Minimum relevance score for an extra snippet chunk to be included

    Returns:
        str: JSON string of cleaned results with title, url, snippet,
        published_date and extra_snippets
    """
    n_results = n_results if n_results is not None else settings.STAAN_MAX_RESULTS
    max_len_snippet = (
        max_len_snippet if max_len_snippet is not None else settings.STAAN_MAX_SNIPPET_LENGTH
    )
    min_score = min_score if min_score is not None else 0

    data = response.json().get("web", {}).get("results", [])
    results = []
    for result in data[:n_results]:
        output = {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "snippet": result.get("snippet", ""),
            "published_date": result.get("published_date", ""),
            "extra_snippets": _collect_extra_snippets(
                result,
                max_len_snippet=max_len_snippet,
                min_score=min_score,
            ),
        }
        results.append(output)
    return json.dumps(results, ensure_ascii=False, indent=2)


@last_model_retry_soft_fail
async def web_search_staan(ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web using the Staan API.

    Args:
        ctx: Execution context used to resolve the user's search market.
        query: Search query. Max 400 characters. Use site:example.com to restrict to a domain.

    Returns:
        ToolReturn: Result of the search.
    """
    market = _resolve_staan_market(ctx)
    logger.info("Staan web search: query=%r market=%s", query, market)
    try:
        response = staan_search(query, market)
        response_data = response.json()
        api_market = response_data.get("query", {}).get("market")
        logger.info("Staan API confirmed market=%s (requested=%s)", api_market, market)
        sources = list({resp.get("url", "") for resp in response_data["web"]["results"]})
        return ToolReturn(
            return_value=format_staan(response),
            metadata={"sources": sources},
        )
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        logger.warning("Staan API HTTP error: status=%s market=%s", status_code, market)
        if status_code == 429:
            raise ModelRetry(
                "The search API is rate limited. Please wait a moment and try again."
            ) from exc
        if status_code is not None and status_code >= 500:
            raise ModelRetry(
                "The search service is temporarily unavailable due to a server error. Retrying..."
            ) from exc
        raise ModelCannotRetry(
            f"Web search failed with a client error (status {status_code}). "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc
    except ModelCannotRetry, ModelRetry:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in web_search_staan: %s", exc)
        raise ModelCannotRetry(
            f"An unexpected error occurred during web search: {type(exc).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc
