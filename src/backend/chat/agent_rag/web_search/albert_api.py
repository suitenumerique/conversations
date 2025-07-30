"""
Albert API web search manager.

Instead of developing a full web search flow, we simply use the Albert API /v1/search endpoint.

See: https://albert.api.etalab.gouv.fr/documentation#tag/Search

Under the hood, on Albert side:
 - It create a temporary collection
 - It performs a web search using the query
 - It returns the results as a list of URls
 - It loads and parses the content of each URL (vectorization)
   and stores the results in the temporary collection
 - It makes a semanctic search on the temporary collection using the query
 - It returns the results as a list of chunks with metadata
 - It deletes the temporary collection
"""

import logging
from urllib.parse import urljoin

from django.conf import settings

import requests

from ..albert_api_constants import Searches, SearchRequest
from ..constants import RAGWebResult, RAGWebResults, RAGWebUsage
from .base import BaseWebSearchManager

logger = logging.getLogger(__name__)


class AlbertWebSearchManager(BaseWebSearchManager):
    """
    A class to manage web search operations using the Albert API.
    """

    def __init__(self):
        """Initializes with the base URL and endpoints for the Albert API."""
        self._base_url = settings.ALBERT_API_URL
        self._headers = {
            "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
            "Content-Type": "application/json",
        }
        self._search_endpoint = urljoin(self._base_url, "/v1/search")

    @staticmethod
    def _clean_url(url: str) -> str:
        """
        Clean the URL by removing the trailing '.html'.
        We want it to fail when Albert fixes the bug that adds '.html' to the end of URLs.
        Note: this is a bad workaround because when fixed it may break existing URLs.

        Args:
            url (str): The URL to clean.

        Returns:
            str: The cleaned URL.
        """
        return url.rsplit(".html", 1)[0]

    def web_search(self, query: str) -> RAGWebResults:
        """
        Perform a web search using the Albert API.

        Args:
            query (str): The search query.

        Returns:
            Searches: A Searches object containing the search results.

        Raises:
            ValueError: If the query is empty.
            requests.HTTPError: If the request to the Albert API fails.
            requests.exceptions.JSONDecodeError: If the response body does not
                contain valid json
        """
        if not query.strip():
            raise ValueError("Search query cannot be empty.")

        search_request = SearchRequest(
            prompt=query,
            web_search=True,  # Enable web search
            web_search_k=settings.RAG_WEB_SEARCH_MAX_RESULTS,  # Number of web search results
            k=settings.RAG_WEB_SEARCH_CHUNK_NUMBER,  # Number of chunks to return from the search
        )

        logger.debug("Albert API search request: %s", search_request.model_dump())

        response = requests.post(
            self._search_endpoint,
            headers=self._headers,
            json=search_request.model_dump(),
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

        searches = Searches(**response.json())

        return RAGWebResults(
            data=[
                RAGWebResult(
                    url=self._clean_url(result.chunk.metadata["document_name"]),
                    content=result.chunk.content,
                    score=result.score,
                )
                for result in searches.data
            ],
            usage=RAGWebUsage(
                prompt_tokens=searches.usage.prompt_tokens,  # pylint: disable=no-member
                completion_tokens=searches.usage.completion_tokens,  # pylint: disable=no-member
            ),
        )
