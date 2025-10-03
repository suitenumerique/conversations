"""Web search tool using Brave for the chat agent."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from django.conf import settings
from django.core.cache import cache

import requests
from pydantic_ai.messages import ToolReturn
from trafilatura import extract, fetch_url
from trafilatura.meta import reset_caches

logger = logging.getLogger(__name__)


def llm_summarize(query: str, text: str) -> str:
    """
    Summarize the text using the LLM summarization agent.

    This is a costly operation and have to be replaced by vector search.
    """
    from chat.agents.summarize import (  # noqa: PLC0415 # pylint: disable=import-outside-toplevel
        SummarizationAgent,
    )

    summarization_agent = SummarizationAgent()

    prompt = f"""
Based on the following request, summarize the following text in a concise manner, 
focusing on the key points regarding the user request. 
he result should be up to 30 lines long.

<user request>
{query}
</user request>

<text to summarize>
{text}
</text to summarize>
"""

    result = summarization_agent.run_sync(prompt)
    return result.output


def _fetch_and_extract(url: str) -> str:
    """Fetch and extract text content from the URL."""
    cache_key = f"web_search_brave:extract:{url}"

    if (document := cache.get(cache_key)) is not None:
        return document

    html = fetch_url(url)
    document = extract(html, include_comments=False, no_fallback=True) or ""
    cache.set(cache_key, document, settings.BRAVE_CACHE_TTL)

    return document


def _extract_and_summarize_snippets(query: str, url: str) -> List[str]:
    """Fetch, extract and summarize text content from the URL.

    Returns a list of snippets (0 or 1 element, preserving existing behavior).
    """
    # Cache by URL to avoid repeated fetch/extract across calls
    document = _fetch_and_extract(url)
    if not document:
        return []

    if not settings.BRAVE_SUMMARIZATION_ENABLED:
        return [document]

    try:
        snippet = llm_summarize(query, document)
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("Summarization failed for %s: %s", url, e)
        snippet = None

    return [snippet] if snippet else []


def _query_brave_api(query: str) -> List[dict]:
    """Query the Brave Search API and return the raw results."""
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.BRAVE_API_KEY,
    }
    data = {
        "q": query,
        "country": settings.BRAVE_SEARCH_COUNTRY,
        "search_lang": settings.BRAVE_SEARCH_LANG,
        "count": settings.BRAVE_MAX_RESULTS,
        "safesearch": settings.BRAVE_SEARCH_SAFE_SEARCH,
        "spellcheck": settings.BRAVE_SEARCH_SPELLCHECK,
        "result_filter": "web,faq,query",
        "extra_snippets": settings.BRAVE_SEARCH_EXTRA_SNIPPETS,
    }
    params = {k: v for k, v in data.items() if v is not None}
    response = requests.get(url, headers=headers, params=params, timeout=settings.BRAVE_API_TIMEOUT)
    response.raise_for_status()

    json_response = response.json()

    # See https://api-dashboard.search.brave.com/app/documentation/web-search/responses#Result
    # & https://api-dashboard.search.brave.com/app/documentation/web-search/responses#SearchResult
    return json_response.get("web", {}).get("results", [])


def web_search_brave(query: str) -> ToolReturn:
    """
    Search the web for up-to-date information

    Args:
        query (str): The query to search for.
    """
    raw_search_results = _query_brave_api(query)

    reset_caches()  # Clear trafilatura caches to avoid memory bloat/leaks

    # Parallelize fetch/extract for results that don't include extra_snippets
    to_process = [
        (idx, r) for idx, r in enumerate(raw_search_results) if not r.get("extra_snippets")
    ]

    if to_process:
        max_workers = min(settings.BRAVE_MAX_WORKERS, len(to_process))
        if max_workers == 1:
            # Avoid overhead of ThreadPoolExecutor if only one task
            for idx, r in to_process:
                raw_search_results[idx]["extra_snippets"] = _extract_and_summarize_snippets(
                    query, r["url"]
                )

        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(_extract_and_summarize_snippets, query, r["url"]): idx
                    for idx, r in to_process
                }
                for future in as_completed(future_map):
                    idx = future_map[future]
                    raw_search_results[idx]["extra_snippets"] = future.result()

    return ToolReturn(
        return_value=[
            {
                "link": result["url"],
                "title": result["title"],
                "extra_snippets": result.get("extra_snippets", []),
            }
            for result in raw_search_results
        ],
        metadata={"sources": {result["url"] for result in raw_search_results}},
    )
