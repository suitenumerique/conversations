"""Web search tool using Staan for the chat agent."""

import logging

from django.conf import settings

import httpx
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail

logger = logging.getLogger(__name__)

STAAN_SEARCH_PATH = "v2/search/web"

_STAAN_MARKET_BY_LANGUAGE_PREFIX = {
    "fr": "fr-fr",
    "en": "en-us",
    "de": "de-de",
}

STAAN_MARKETS = frozenset(_STAAN_MARKET_BY_LANGUAGE_PREFIX.values())
STAAN_DEFAULT_MARKET = "en-us"


def resolve_staan_market(language: str | None) -> str:
    """Map a UI language code to a supported Staan search market."""
    user_lang = (language or settings.LANGUAGE_CODE or "").lower()
    if user_lang in STAAN_MARKETS:
        return user_lang
    prefix = user_lang.split("-")[0] if user_lang else ""
    if prefix in _STAAN_MARKET_BY_LANGUAGE_PREFIX:
        return _STAAN_MARKET_BY_LANGUAGE_PREFIX[prefix]
    return STAAN_DEFAULT_MARKET


async def staan_search(query: str, market: str) -> dict:
    """
    Perform a search using the Staan API.

    The per-url snippet limits are enforced by the API itself so we don't pay for
    chunks we would discard afterwards. The result count is not configurable: the API
    only accepts `count=10`, its own default, so a search always returns ten results
    and `max_snippets` is the only lever on how much text each of them contributes.

    Args:
        query: User query string.
        market: Staan search market (e.g. fr-fr, en-us, de-de).

    Returns:
        dict: Parsed JSON payload from the Staan API.

    """
    missing_settings = [
        name for name in ("STAAN_API_KEY", "STAAN_API_URL") if not getattr(settings, name)
    ]
    if missing_settings:
        raise ModelCannotRetry(
            f"Missing Staan configuration: {', '.join(missing_settings)}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        )

    endpoint = f"{settings.STAAN_API_URL.rstrip('/')}/{STAAN_SEARCH_PATH}"

    params = {
        "q": query,
        "market": market,
        "extra_snippets": "true" if settings.STAAN_SEARCH_EXTRA_SNIPPETS else "false",
        "max_snippets": settings.STAAN_MAX_SNIPPETS_PER_URL,
        "min_score": settings.STAAN_MIN_SNIPPET_SCORE,
    }

    headers = {
        "Authorization": f"Bearer {settings.STAAN_API_KEY}",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.STAAN_API_TIMEOUT) as client:
            response = await client.get(
                endpoint,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    # httpx renders the failing request url, query string included, into str(exc), so
    # the logs below report the status and the endpoint instead: never the user's query.
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 429:
            logger.warning("Staan API rate limited (status %s) on %s", status_code, endpoint)
            raise ModelRetry(
                "The search API is rate limited. Please wait a moment and try again."
            ) from exc
        if status_code >= 500:
            logger.warning("Staan API server error (status %s) on %s", status_code, endpoint)
            raise ModelRetry(
                "The search service is temporarily unavailable due to a server error. Retrying..."
            ) from exc

        logger.error("Staan API client error (status %s) on %s", status_code, endpoint)
        raise ModelCannotRetry(
            f"Web search failed with a client error (status {status_code}). "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc
    except httpx.TimeoutException as exc:
        logger.warning("Staan API timeout on %s", endpoint)
        raise ModelRetry("The search request timed out. Retrying with a fresh attempt...") from exc
    except httpx.HTTPError as exc:
        logger.warning("Staan API connection error on %s: %s", endpoint, type(exc).__name__)
        raise ModelRetry(
            f"Connection error while searching the web: {type(exc).__name__}. Retrying..."
        ) from exc


def _collect_extra_snippets(result: dict) -> list[str]:
    """Extract the extra snippet chunks of a Staan result.

    The chunks are kept whole: the API already bounds both their number
    (`max_snippets`) and their size (300 to 1800 characters), and it returns them
    ranked by score, so trimming here would only discard the best evidence.
    """
    return [
        chunk
        for item in result.get("extra_snippets") or []
        if (chunk := item.get("chunk", "") if isinstance(item, dict) else str(item))
    ]


def format_staan(payload: dict) -> dict:
    """
    Build the tool payload from a Staan API response.

    Results are keyed by rank so the model can cite a source by its index, and
    carry the publication date Staan provides. Results without a url or without any
    snippet are dropped; `metadata["sources"]` is built from the urls that survive.

    Nothing is trimmed here. How much text a search sends to the model is decided
    server-side by `max_snippets`, which the API applies to its own score ranking.

    Args:
        payload: Parsed JSON payload from the Staan API.

    Returns:
        dict: Results indexed by rank, with title, url, snippets and published_date.
    """
    formatted_results = {}

    for result in payload.get("web", {}).get("results", []) or []:
        url = result.get("url")
        if not url:
            continue

        snippets = _collect_extra_snippets(result)
        if main_snippet := (result.get("snippet") or ""):
            snippets.insert(0, main_snippet)
        if not snippets:
            continue

        formatted_results[str(len(formatted_results))] = {
            "url": url,
            "title": result.get("title") or url,
            "snippets": snippets,
            "published_date": result.get("published_date", ""),
        }

    return formatted_results


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
    market = resolve_staan_market(ctx.deps.language)
    logger.debug("Starting Staan web search for market %s", market)
    try:
        payload = await staan_search(query, market)
        logger.debug(
            "Staan API confirmed market=%s (requested=%s)",
            payload.get("query", {}).get("market"),
            market,
        )

        formatted_results = format_staan(payload)
        if not formatted_results:
            raise ModelRetry(
                "No valid search results were extracted from the web pages. "
                "Retrying the search to find better sources..."
            )

        return ToolReturn(
            return_value=formatted_results,
            metadata={"sources": {result["url"] for result in formatted_results.values()}},
        )

    except ModelCannotRetry, ModelRetry:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in web_search_staan: %s", exc)
        raise ModelCannotRetry(
            f"An unexpected error occurred during web search: {type(exc).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc
