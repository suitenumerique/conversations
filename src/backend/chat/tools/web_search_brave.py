"""Web search tool using Brave for the chat agent."""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from django.conf import settings
from django.core.cache import cache
from django.utils.module_loading import import_string

import requests
from pydantic_ai import RunContext, RunUsage
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


def _fetch_and_store(url: str, document_store) -> None:
    """Fetch, extract and store text content from the URL in the document store."""
    document = _fetch_and_extract(url)
    if document:
        document_store.store_document(url, document)


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


def format_tool_return(raw_search_results: List[dict]) -> ToolReturn:
    """Format the raw search results into a ToolReturn object."""
    return ToolReturn(
        # Format return value "mistral-like": https://docs.mistral.ai/capabilities/citations/
        return_value={
            str(idx): {
                "url": result["url"],
                "title": result["title"],
                "snippets": result.get("extra_snippets", []),
            }
            for idx, result in enumerate(raw_search_results)
            if result.get("extra_snippets", [])
        },
        metadata={
            "sources": {
                result["url"] for result in raw_search_results if result.get("extra_snippets", [])
            }
        },
    )


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

    return format_tool_return(raw_search_results)


def web_search_brave_with_document_backend(ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web for up-to-date information

    Args:
        ctx (RunContext): The run context containing the conversation.
        query (str): The query to search for.
    """
    raw_search_results = _query_brave_api(query)

    reset_caches()  # Clear trafilatura caches to avoid memory bloat/leaks

    # Store documents in a temporary document store for RAG search
    document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
    with document_store_backend.temporary_collection(f"tmp-{uuid.uuid4()}") as document_store:
        max_workers = min(settings.BRAVE_MAX_WORKERS, len(raw_search_results))
        if max_workers == 1:
            for result in raw_search_results:
                # Fetch and extract document content
                _fetch_and_store(result["url"], document_store)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_fetch_and_store, result["url"], document_store)
                    for result in raw_search_results
                ]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:  # pylint: disable=broad-except
                        logger.exception("Error fetching/storing document: %s", e)

        rag_results = document_store.search(query)

        ctx.usage += RunUsage(
            input_tokens=rag_results.usage.prompt_tokens,
            output_tokens=rag_results.usage.completion_tokens,
        )

        # Map RAG results back to raw search results to include extra_snippets
        # Suboptimal O(N^2) but N is small...
        for rag_result in rag_results.data:
            for result in raw_search_results:
                if result["url"] == rag_result.url:
                    result.setdefault("extra_snippets", []).append(rag_result.content)
                    break

    return format_tool_return(raw_search_results)
