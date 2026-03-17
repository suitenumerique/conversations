"""Web search tool using Brave for the chat agent."""

import asyncio
import logging
import re
import uuid
from typing import List

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string
from django.utils.text import slugify

import httpx
from asgiref.sync import sync_to_async
from pydantic_ai import RunContext, RunUsage
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from trafilatura import extract
from trafilatura.meta import reset_caches

from chat.models import ChatConversationAttachment
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail
from core.file_upload.enums import AttachmentStatus

logger = logging.getLogger(__name__)

MAX_INLINE_CONTENT_CHARS = 1000
DOCS_HOST = "docs.numerique.gouv.fr"


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


def _normalize_llm_context_results(json_response: dict) -> List[dict]:
    """Normalize Brave LLM context payload into our common result shape."""
    generic_results = json_response.get("grounding", {}).get("generic", []) or []
    normalized_results: List[dict] = []
    for item in generic_results:
        item_url = item.get("url")
        if not item_url:
            continue

        normalized_results.append(
            {
                "url": item_url,
                # Fallback to URL if no title is provided
                "title": item.get("title") or item_url,
                # `snippets` is already a list
                "snippets": item.get("snippets") or [],
            }
        )
    return normalized_results


async def _query_brave_api_with_endpoint_async(url: str, data: dict) -> List[dict]:
    """Query a Brave endpoint and return raw results normalized to our schema."""
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.BRAVE_API_KEY,
    }
    params = {k: v for k, v in data.items() if v is not None}

    try:
        async with httpx.AsyncClient(timeout=settings.BRAVE_API_TIMEOUT) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            json_response = response.json()

            # LLM context API: results are under `grounding.generic`
            # See: https://api-dashboard.search.brave.com/documentation/services/llm-context
            if "grounding" in json_response:
                return _normalize_llm_context_results(json_response)

            # Fallback for classic web search JSON shape
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


async def _query_brave_llm_context_api_async(query: str) -> List[dict]:
    """Query Brave LLM context endpoint and return normalized results."""
    logger.debug("Using LLM context endpoint")
    return await _query_brave_api_with_endpoint_async(
        "https://api.search.brave.com/res/v1/llm/context",
        {
            "q": query,
            "country": settings.BRAVE_SEARCH_COUNTRY,
            "search_lang": settings.BRAVE_SEARCH_LANG,
            "count": settings.BRAVE_MAX_RESULTS,
            "safesearch": settings.BRAVE_SEARCH_SAFE_SEARCH,
            "spellcheck": settings.BRAVE_SEARCH_SPELLCHECK,
            "result_filter": "web,faq,query",
            "extra_snippets": settings.BRAVE_SEARCH_EXTRA_SNIPPETS,
            "maximum_number_of_urls": settings.BRAVE_MAX_RESULTS,
            "maximum_number_of_tokens": settings.BRAVE_MAX_TOKENS,
            "maximum_number_of_snippets": settings.BRAVE_MAX_SNIPPETS,
            "maximum_number_of_snippets_per_url": settings.BRAVE_MAX_SNIPPETS_PER_URL,
        },
    )


async def _query_brave_web_search_api_async(query: str) -> List[dict]:
    """Query Brave classic web search endpoint and return normalized results."""
    logger.debug("Using classic web search endpoint")
    return await _query_brave_api_with_endpoint_async(
        "https://api.search.brave.com/res/v1/web/search",
        {
            "q": query,
            "country": settings.BRAVE_SEARCH_COUNTRY,
            "search_lang": settings.BRAVE_SEARCH_LANG,
            "count": settings.BRAVE_MAX_RESULTS,
            "safesearch": settings.BRAVE_SEARCH_SAFE_SEARCH,
            "spellcheck": settings.BRAVE_SEARCH_SPELLCHECK,
            "result_filter": "web,faq,query",
            "extra_snippets": settings.BRAVE_SEARCH_EXTRA_SNIPPETS,
        },
    )


def format_tool_return(raw_search_results: List[dict]) -> ToolReturn:
    """Build the tool payload from Brave results.

    Keep only sources that have non-empty snippets and prefer `snippets` over
    `extra_snippets` when both are present.
    """
    formatted_results = {}
    sources = set()

    for idx, result in enumerate(raw_search_results):
        logger.debug("Formatting result: %s", result)
        snippets = result.get("snippets") or result.get("extra_snippets") or []
        if not snippets:
            continue

        formatted_results[str(idx)] = {
            "url": result["url"],
            "title": result["title"],
            "snippets": snippets,
        }
        sources.add(result["url"])

    return ToolReturn(
        return_value=formatted_results,
        metadata={"sources": sources},
    )


@last_model_retry_soft_fail
async def web_search_brave(_ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web for up-to-date information.
    This function use the classic websearch endpoint of the Brave API.
    URLs are then fetched and extracted using trafilatura.
    The extracted text is then summarized using the LLM summarization agent.
    The results are then formatted and returned.

    Args:
        _ctx (RunContext): The run context, used by the wrapper.
        query (str): The query to search for.
    """
    logger.debug("Starting classic web search without RAG backend for query: %s", query)
    try:
        raw_search_results = await _query_brave_web_search_api_async(query)

        await sync_to_async(reset_caches)()  # Clear trafilatura caches to avoid memory bloat/leaks

        # Parallelize fetch/extract only for results that don't already include any snippets
        # (neither Brave `snippets` nor `extra_snippets`).
        to_process = [
            (idx, r)
            for idx, r in enumerate(raw_search_results)
            if not r.get("extra_snippets") and not r.get("snippets")
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

    except ModelCannotRetry, ModelRetry:
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
async def web_search_brave_llm_context(_ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web using Brave LLM context endpoint (no RAG post-processing).
    This function use the LLM context endpoint of the Brave API.
    The results are then formatted and returned.
    """
    logger.debug("Starting web search with LLM context endpoint for query: %s", query)
    try:
        raw_search_results = await _query_brave_llm_context_api_async(query)
        formatted_result = format_tool_return(raw_search_results)
        if not formatted_result.return_value:
            raise ModelRetry("No valid search results were extracted from Brave LLM context.")
        return formatted_result
    except ModelCannotRetry, ModelRetry:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in web_search_brave_llm_context: %s", exc)
        raise ModelCannotRetry(
            f"An unexpected error occurred during web search: {type(exc).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc


@last_model_retry_soft_fail
async def web_search_brave_with_document_backend(ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web for up-to-date information using RAG backend.
    URLs are then fetched and extracted using trafilatura.
    The extracted text is then stored in a temporary document store for RAG search.
    The RAG search is then performed and the results are returned.

    Args:
        ctx (RunContext): The run context containing the conversation.
        query (str): The query to search for.
    """
    logger.debug("Starting web search with RAG backend for query: %s", query)
    try:
        raw_search_results = await _query_brave_web_search_api_async(query)

        # Clear trafilatura caches in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, reset_caches)

        # Store documents in a temporary document store for RAG search
        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        # Create temporary collection
        temp_collection_name = f"tmp-{uuid.uuid4()}"
        try:
            async with document_store_backend.temporary_collection_async(
                temp_collection_name, session=ctx.deps.session
            ) as document_store:
                # Fetch and store all documents concurrently
                tasks = [
                    _fetch_and_store_async(
                        result["url"],
                        document_store,
                        user_sub=ctx.deps.user.sub,
                        session=ctx.deps.session,
                    )
                    for result in raw_search_results
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Perform RAG search
                rag_results = await document_store.asearch(
                    query=query,
                    results_count=settings.BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER,
                    session=ctx.deps.session,
                    user_sub=ctx.deps.user.sub,
                )
                logger.debug("RAG search returned:  %s", rag_results)

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
    except ModelCannotRetry, ModelRetry:
        # Re-raise these as-is
        raise
    except Exception as e:
        # Unexpected error - stop and inform user
        logger.exception("Unexpected error in web_search_brave_with_document_backend: %s", e)
        raise ModelCannotRetry(
            f"An unexpected error occurred during web search with RAG: {type(e).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from e


@last_model_retry_soft_fail
async def web_search(ctx: RunContext, query: str | None = None, url: str | None = None) -> ToolReturn:
    """
    Unified web search tool supporting three usage modes:

    - **Snippet mode (query only)**:
      Perform a Brave LLM-context search from a textual query and return
      snippets from the results.
    - **URL mode (url only)**:
      Fetch and return the content of a given URL. For small pages, the full
      extracted text is returned inline. For large pages, the content is
      indexed into the conversation's document base when possible and only a
      preview is returned (plus guidance to use document tools).
    - **URL+RAG mode (query and url)**:
      Fetch and index the given URL into the conversation's document base, then
      run a RAG search on this document using the provided query and return the
      most relevant chunks.
    """
    # Snippet mode: query only — reuse main's LLM context endpoint path
    if query and not url:
        return await web_search_brave_llm_context(ctx, query)

    # URL-only or URL+RAG mode require at least a URL
    if not url and not query:
        raise ModelCannotRetry(
            "web_search requires either a non-empty query or a URL. "
        )

    # URL mode: handle Docs Numérique URLs specially to use their markdown API,
    # then fall back to generic HTML extraction.
    docs_match = re.search(r"https?://(?:www\.)?docs\.numerique\.gouv\.fr/docs/([^/?#]+)", url or "")
    if docs_match:
        docs_id = docs_match.group(1)
        api_url = f"https://{DOCS_HOST}/api/v1.0/documents/{docs_id}/content/?content_format=markdown"
        try:
            async with httpx.AsyncClient(timeout=settings.BRAVE_API_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(api_url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # pragma: no cover - network / JSON edge cases
            logger.warning("Error fetching Docs content for %s via %s: %s", url, api_url, exc, exc_info=True)
            return ToolReturn(
                return_value={
                    "url": url,
                    "error": f"Failed to fetch Docs content: {exc}",
                }
            )

        content = data.get("content") or ""
        if not content:
            return ToolReturn(
                return_value={
                    "url": url,
                    "error": "Content empty or private for this Docs URL.",
                }
            )

        snippet = content[:MAX_INLINE_CONTENT_CHARS]
        return ToolReturn(
            return_value={
                "url": url,
                "content": snippet,
                "source": DOCS_HOST,
            },
            metadata={"sources": {url}},
        )

    # Generic URL / URL+RAG mode: reuse the lightweight extractor already used in
    # the Brave RAG backend. This keeps behavior consistent and avoids
    # re-implementing RAG wiring here.
    try:
        document = await _fetch_and_extract_async(url)
    except DocumentFetchError as exc:
        logger.warning("Failed to fetch URL in web_search URL mode: %s", exc, exc_info=True)
        return ToolReturn(
            return_value={
                "url": url,
                "error": f"Error while fetching URL: {exc}",
            }
        )

    if not document:
        return ToolReturn(
            return_value={
                "url": url,
                "error": "No textual content could be extracted from the URL.",
            }
        )

    # For very long content, store in the conversation's RAG collection when possible
    # and return only a preview with guidance to use RAG tools. When a query is also
    # provided, run a RAG search over this document and return the most relevant chunks.
    if len(document) > MAX_INLINE_CONTENT_CHARS or query:
        deps = getattr(ctx, "deps", None)
        conversation = getattr(deps, "conversation", None) if deps else None
        user = getattr(deps, "user", None) if deps else None
        session = getattr(deps, "session", None) if deps else None

        stored_in_rag = False
        attachment_created = False
        document_store = None

        if conversation and user:
            try:
                document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
                # Ensure a collection exists for this conversation (async version of
                # the logic in AIAgentService._handle_input_documents).
                document_store = document_store_backend(conversation.collection_id)
                if not document_store.collection_id:
                    collection_id = await document_store.acreate_collection(
                        name=f"conversation-{conversation.pk}",
                    )
                    conversation.collection_id = str(collection_id)
                    await conversation.asave(update_fields=["collection_id", "updated_at"])

                await document_store.astore_document(
                    name=url,
                    content=document,
                    user_sub=user.sub,
                    session=session,
                )
                stored_in_rag = True

                # Also create a text attachment so tools like document_summarize
                # can operate on this content as if it had been uploaded.
                safe_name = slugify(url)[:100] or "document"
                file_name = f"{safe_name}.txt"
                key = f"{conversation.pk}/attachments/{file_name}"

                await sync_to_async(default_storage.save)(
                    key,
                    ContentFile(document.encode("utf-8")),
                )
                await sync_to_async(ChatConversationAttachment.objects.create)(
                    conversation=conversation,
                    uploaded_by=user,
                    upload_state=AttachmentStatus.READY,
                    key=key,
                    file_name=file_name,
                    content_type="text/plain; charset=utf-8",
                    size=len(document.encode("utf-8")),
                    conversion_from=url,
                )
                attachment_created = True
            except Exception as exc:  # pragma: no cover - best-effort storage
                logger.warning(
                    "Failed to store URL content in RAG or attachments for %s: %s",
                    url,
                    exc,
                    exc_info=True,
                )

        # If a query is also provided, run a RAG search over this single document
        # and return the most relevant chunks instead of a generic preview.
        if query and document_store and conversation and user:
            try:
                rag_results = await document_store.asearch(
                    query=query,
                    results_count=settings.BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER,
                    session=session,
                    user_sub=user.sub,
                )

                ctx.usage += RunUsage(
                    input_tokens=rag_results.usage.prompt_tokens,
                    output_tokens=rag_results.usage.completion_tokens,
                )

                return ToolReturn(
                    return_value={
                        str(idx): {
                            "url": url,
                            "snippets": result.content,
                        }
                        for idx, result in enumerate(rag_results.data)
                    },
                    metadata={"sources": {url}},
                )
            except Exception as exc:  # pragma: no cover - best-effort RAG search
                logger.warning(
                    "RAG search over URL content failed for %s: %s", url, exc, exc_info=True
                )

        # Fallback: behave like pure URL mode with preview and guidance
        preview = document[:MAX_INLINE_CONTENT_CHARS]
        return ToolReturn(
            return_value={
                "url": url,
                "stored_in_rag": stored_in_rag,
                "attachment_created": attachment_created,
                "content_preview": preview,
                "content": (
                    "Le contenu de cette ressource est volumineux. Tu dois éviter de le coller "
                    "intégralement dans ta réponse. Résume ou extrait uniquement les passages "
                    "pertinents. "
                    + (
                        "Il a été indexé dans la base de documents de la conversation : utilise "
                        "l’outil `document_search_rag` ou `document_summarize` avec une requête "
                        "précise pour retrouver ou résumer les informations nécessaires."
                        if stored_in_rag or attachment_created
                        else "Si le document est présent dans la base de documents de la conversation, "
                        "utilise l’outil `document_search_rag` ou `document_summarize` avec une requête "
                        "précise pour retrouver ou résumer les informations nécessaires."
                    )
                ),
            },
            metadata={"sources": {url}},
        )

    # Small document and no query: simple inline content
    content = document[:MAX_INLINE_CONTENT_CHARS]
    return ToolReturn(
        return_value={
            "url": url,
            "content": content,
        },
        metadata={"sources": {url}},
    )
