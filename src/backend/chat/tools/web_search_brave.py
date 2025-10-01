"""Web search tool using Brave for the chat agent."""

from django.conf import settings

import requests
from pydantic_ai.messages import ToolReturn
from trafilatura import extract, fetch_url
from trafilatura.meta import reset_caches


def web_search_brave(query: str) -> ToolReturn:
    """
    Search the web for up-to-date information

    Args:
        query (str): The query to search for.
    """
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

    raw_search_results = json_response.get("web", {}).get("results", [])

    # See https://api-dashboard.search.brave.com/app/documentation/web-search/responses#Result
    # & https://api-dashboard.search.brave.com/app/documentation/web-search/responses#SearchResult

    reset_caches()
    for result in raw_search_results:
        if not result.get("extra_snippets"):
            document = extract(fetch_url(result["url"]), include_comments=False, no_fallback=True)
            result["extra_snippets"] = [document] if document else []

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
