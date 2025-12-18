"""Web search tool using Brave for the chat agent."""

import asyncio
import logging
import uuid
from typing import List

from django.conf import settings
from django.core.cache import cache
from django.utils.module_loading import import_string
from django.utils.text import slugify

import httpx
from asgiref.sync import sync_to_async
from pydantic_ai import RunContext, RunUsage
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from trafilatura import extract
from trafilatura.meta import reset_caches

from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail

logger = logging.getLogger(__name__)


class WebSearchError(Exception):
    """Base exception for web search errors."""


class BraveAPIError(WebSearchError):
    """Error when calling Brave API."""


class DocumentFetchError(WebSearchError):
    """Error when fetching or extracting documents."""


async def llm_summarize_async(query: str, text: str) -> str:
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
The result should be up to 30 lines long.

<user request>
{query}
</user request>

<text to summarize>
{text}
</text to summarize>
"""

    result = await summarization_agent.run(prompt)
    return result.output


async def _fetch_url_async(url: str, timeout: int = 30) -> str:
    """Fetch URL content asynchronously."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def _fetch_and_extract_async(url: str) -> str:
    """Fetch and extract text content from the URL asynchronously."""
    cache_key = f"web_search_brave:extract:{slugify(url)}"

    # Check cache first
    if (document := await cache.aget(cache_key)) is not None:
        return document

    try:
        # Fetch HTML
        html = await _fetch_url_async(url, timeout=settings.BRAVE_API_TIMEOUT)

        # Extract text in thread pool (trafilatura is CPU-bound)
        document = await sync_to_async(extract)(html, include_comments=False, no_fallback=True)

        # Cache the result
        await cache.aset(cache_key, document, settings.BRAVE_CACHE_TTL)
        return document

    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching %s: %s", url, e, exc_info=True)
        raise DocumentFetchError(f"Failed to fetch {url}: {e}") from e
    except Exception as e:
        logger.warning("Error extracting content from %s: %s", url, e, exc_info=True)
        raise DocumentFetchError(f"Failed to extract content from {url}: {e}") from e


async def _extract_and_summarize_snippets_async(query: str, url: str) -> List[str]:
    """Fetch, extract and summarize text content from the URL.

    Returns a list of snippets (0 or 1 element, preserving existing behavior).
    """
    try:
        document = await _fetch_and_extract_async(url)
        if not document:
            return []

        if not settings.BRAVE_SUMMARIZATION_ENABLED:
            return [document]

        try:
            snippet = await llm_summarize_async(query, document)
            return [snippet] if snippet else []
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Summarization failed for %s: %s", url, e)
            # Fallback to raw document if summarization fails
            return [document]

    except DocumentFetchError:
        # Document fetch failed, return empty
        return []


async def _fetch_and_store_async(url: str, document_store, **kwargs) -> None:
    """Fetch, extract and store text content from the URL in the document store."""

    try:
        document = await _fetch_and_extract_async(url)

        logger.debug("Fetched document: %s", document)

        if document:
            await document_store.astore_document(url, document, **kwargs)
    except DocumentFetchError as e:
        logger.warning("Failed to fetch and store %s: %s", url, e)
        # Continue with other documents


async def _query_brave_api_async(query: str) -> List[dict]:
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

    try:
        async with httpx.AsyncClient(timeout=settings.BRAVE_API_TIMEOUT) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            json_response = response.json()

            # https://api-dashboard.search.brave.com/app/documentation/web-search/responses#Result
            return json_response.get("web", {}).get("results", [])

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Rate limit - retryable
            logger.warning("Brave API rate limited: %s", e)
            raise ModelRetry(
                "The search API is rate limited. Please wait a moment and try again."
            ) from e
        if e.response.status_code >= 500:
            # Server error - retryable
            logger.warning("Brave API error: %s", e)
            raise ModelRetry(
                "The search service is temporarily unavailable due to a server error. Retrying..."
            ) from e

        # Client error (4xx) - not retryable, stop and inform user
        logger.error("Brave API client error: %s", e)
        raise ModelCannotRetry(
            f"Web search failed with a client error (status {e.response.status_code}). "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from e
    except httpx.TimeoutException as e:
        # Timeout - retryable
        logger.warning("Brave API timeout: %s", e)
        raise ModelRetry("The search request timed out. Retrying with a fresh attempt...") from e
    except httpx.HTTPError as e:
        # Other HTTP errors - retryable
        logger.warning("Brave API connection error: %s", e)
        raise ModelRetry(
            f"Connection error while searching the web: {type(e).__name__}. Retrying..."
        ) from e
    except Exception as e:
        # Unexpected errors - not retryable, stop completely
        logger.exception("Unexpected error querying Brave API: %s", e)
        raise ModelCannotRetry(
            f"An unexpected error occurred with the search service: {type(e).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from e


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


@last_model_retry_soft_fail
async def web_search_brave(_ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web for up-to-date information

    Args:
        _ctx (RunContext): The run context, used by the wrapper.
        query (str): The query to search for.
    """
    try:
        raw_search_results = await _query_brave_api_async(query)

        await sync_to_async(reset_caches)()  # Clear trafilatura caches to avoid memory bloat/leaks

        # Parallelize fetch/extract for results that don't include extra_snippets
        to_process = [
            (idx, r) for idx, r in enumerate(raw_search_results) if not r.get("extra_snippets")
        ]

        if to_process:
            # Process all URLs concurrently
            tasks = [
                _extract_and_summarize_snippets_async(query, r["url"]) for idx, r in to_process
            ]
            results = await asyncio.gather(*tasks, return_exceptions=False)

            # Update raw_search_results with extracted snippets
            for (idx, _), snippets in zip(to_process, results, strict=True):
                raw_search_results[idx]["extra_snippets"] = snippets

        formatted_result = format_tool_return(raw_search_results)

        # Check if we got any valid results
        if not formatted_result.return_value:
            raise ModelRetry(
                "No valid search results were extracted from the web pages. "
                "Retrying the search to find better sources..."
            )

        return formatted_result

    except (ModelCannotRetry, ModelRetry):
        # Re-raise these as-is
        raise
    except Exception as exc:
        # Unexpected error in our code - stop and inform user
        logger.exception("Unexpected error in web_search_brave: %s", exc)
        raise ModelCannotRetry(
            f"An unexpected error occurred during web search: {type(exc).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc


@last_model_retry_soft_fail
async def web_search_brave_with_document_backend(ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web for up-to-date information using RAG backend

    Args:
        ctx (RunContext): The run context containing the conversation.
        query (str): The query to search for.
    """
    logger.info("Starting web search with RAG backend for query: %s", query)
    try:
        raw_search_results = await _query_brave_api_async(query)

        # Clear trafilatura caches in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, reset_caches)

        # Store documents in a temporary document store for RAG search
        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        # Create temporary collection
        temp_collection_name = f"tmp-{uuid.uuid4()}"
        try:
            async with document_store_backend.temporary_collection_async(
                temp_collection_name
            ) as document_store:
                # Fetch and store all documents concurrently
                tasks = [
                    _fetch_and_store_async(result["url"], document_store)
                    for result in raw_search_results
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Perform RAG search
                rag_results = await document_store.asearch(
                    query,
                    results_count=settings.BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER,
                )
                logger.info("RAG search returned:  %s", rag_results)

                ctx.usage += RunUsage(
                    input_tokens=rag_results.usage.prompt_tokens,
                    output_tokens=rag_results.usage.completion_tokens,
                )

                # Map RAG results back to raw search results to include extra_snippets
                for rag_result in rag_results.data:
                    for result in raw_search_results:
                        if result["url"] == rag_result.url:
                            result.setdefault("extra_snippets", []).append(rag_result.content)
                            break

        except Exception as exc:
            logger.exception("Error with document store: %s", exc)
            raise ModelRetry(
                f"Document storage temporarily failed: {type(exc).__name__}. "
                "Retrying the operation..."
            ) from exc

        formatted_result = format_tool_return(raw_search_results)

        # Check if we got any valid results
        if not formatted_result.return_value:
            raise ModelRetry("No valid search results were extracted.")

        return formatted_result
    except (ModelCannotRetry, ModelRetry):
        # Re-raise these as-is
        raise
    except Exception as e:
        # Unexpected error - stop and inform user
        logger.exception("Unexpected error in web_search_brave_with_document_backend: %s", e)
        raise ModelCannotRetry(
            f"An unexpected error occurred during web search with RAG: {type(e).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from e
