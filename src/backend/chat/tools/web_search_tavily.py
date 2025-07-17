"""Web search tool using Tavily for the chat agent."""
import requests
from agents import function_tool

from django.conf import settings

@function_tool(name_override="tavily_web_search")
def agent_web_search_tavily(query: str) -> list[dict]:
    """
    Search the web for up-to-date information

    Args:
        query (str): The query to search for.

    Returns:
        list[dict]: A list of search results, each represented as a dictionary.
    """
    url = "https://api.tavily.com/search"
    data = {
        "query": query,
        "api_key": settings.TAVILY_API_KEY,
        "max_results": settings.TAVILY_MAX_RESULTS,
    }
    response = requests.post(url, json=data)
    response.raise_for_status()

    json_response = response.json()

    raw_search_results = json_response.get("results", [])

    return [
        dict(
            link=result["url"],
            title=result.get("title", ""),
            snippet=result.get("content"),
        )
        for result in raw_search_results
    ]
