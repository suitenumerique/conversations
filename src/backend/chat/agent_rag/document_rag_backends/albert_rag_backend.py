"""Implementation of the Albert API for RAG document search."""

import json
import logging
from io import BytesIO
from typing import List, Optional
from urllib.parse import urljoin

from django.conf import settings
from django.utils.module_loading import import_string

import httpx
import requests

from chat.agent_rag.albert_api_constants import Searches
from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend

logger = logging.getLogger(__name__)


class AlbertRagBackend(BaseRagBackend):  # pylint: disable=too-many-instance-attributes
    """
    This class is a placeholder for the Albert API implementation.
    It is designed to be used with the RAG (Retrieval-Augmented Generation) document search system.

    It provides methods to:
    - Create a collection for the search operation.
    - Store parsed documents in the Albert collection.
    - Perform a search operation using the Albert API.
    """

    def __init__(
        self,
        collection_id: Optional[str] = None,
        read_only_collection_id: Optional[List[str]] = None,
    ):
        # Initialize any necessary parameters or configurations here
        super().__init__(collection_id, read_only_collection_id)
        self._base_url = settings.ALBERT_API_URL
        self._headers = {
            "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
        }
        self._collections_endpoint = urljoin(self._base_url, "/v1/collections")
        self._documents_endpoint = urljoin(self._base_url, "/v1/documents")
        self._search_endpoint = urljoin(self._base_url, "/v1/search")
        self._default_collection_description = "Temporary collection for RAG document search"
        parser_class = import_string(settings.RAG_DOCUMENT_PARSER)
        self.parser = parser_class()

    def create_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        response = requests.post(
            self._collections_endpoint,
            headers=self._headers,
            json={
                "name": name,
                "description": description or self._default_collection_description,
                "visibility": "private",
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()
        self.collection_id = str(response.json()["id"])
        return self.collection_id

    async def acreate_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.post(
                self._collections_endpoint,
                headers=self._headers,
                json={
                    "name": name,
                    "description": description or self._default_collection_description,
                    "visibility": "private",
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            response.raise_for_status()

        self.collection_id = str(response.json()["id"])
        return self.collection_id

    def delete_collection(self, **kwargs) -> None:
        """
        Delete the current collection
        """
        response = requests.delete(
            urljoin(f"{self._collections_endpoint}/", self.collection_id),
            headers=self._headers,
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

    async def adelete_collection(self, **kwargs) -> None:
        """
        Asynchronously delete the current collection
        """
        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.delete(
                urljoin(f"{self._collections_endpoint}/", self.collection_id),
                headers=self._headers,
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            response.raise_for_status()

    def store_document(self, name: str, content: str, **kwargs) -> None:
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
            **kwargs: Additional arguments.
        """
        response = requests.post(
            urljoin(self._base_url, self._documents_endpoint),
            headers=self._headers,
            files={
                "file": (f"{name}.md", BytesIO(content.encode("utf-8")), "text/markdown"),
                "collection": (None, int(self.collection_id)),
                "metadata": (None, json.dumps({"document_name": name})),  # undocumented API
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        logger.debug(response.json())
        response.raise_for_status()

    async def astore_document(self, name: str, content: str, **kwargs) -> None:
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
            **kwargs: Additional arguments.
        """
        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.post(
                urljoin(self._base_url, self._documents_endpoint),
                headers=self._headers,
                files={
                    "file": (f"{name}.md", BytesIO(content.encode("utf-8")), "text/markdown"),
                },
                data={
                    "collection": int(self.collection_id),
                    "metadata": json.dumps({"document_name": name}),  # undocumented API
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            logger.debug(response.json())
            response.raise_for_status()

    def search(self, query: str, results_count: int = 4, **kwargs) -> RAGWebResults:
        """
        Perform a search using the Albert API based on the provided query.

        Args:
            query (str): The search query.
            results_count (int): The number of results to return.
            **kwargs: Additional arguments.

        Returns:
            RAGWebResults: The search results.
        """
        collection_ids = self.get_all_collection_ids()  # might raise RuntimeError

        response = requests.post(
            urljoin(self._base_url, self._search_endpoint),
            headers=self._headers,
            json={
                "collections": collection_ids,
                "prompt": query,
                "score_threshold": 0.6,
                "k": results_count,  # Number of chunks to return from the search
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

        searches = Searches(**response.json())

        return RAGWebResults(
            data=[
                RAGWebResult(
                    url=result.chunk.metadata["document_name"],
                    content=result.chunk.content,
                    score=result.score,
                )
                for result in searches.data
            ],
            usage=RAGWebUsage(
                prompt_tokens=searches.usage.prompt_tokens,
                completion_tokens=searches.usage.completion_tokens,
            ),
        )

    async def asearch(self, query, results_count: int = 4, **kwargs) -> RAGWebResults:
        """
        Perform an asynchronous search using the Albert API based on the provided query.

        Args:
            query (str): The search query.
            results_count (int): The number of results to return.
            **kwargs: Additional arguments.

        Returns:
            RAGWebResults: The search results.
        """
        collection_ids = self.get_all_collection_ids()  # might raise RuntimeError

        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.post(
                urljoin(self._base_url, self._search_endpoint),
                headers=self._headers,
                json={
                    "collections": collection_ids,
                    "prompt": query,
                    "score_threshold": 0.6,
                    "k": results_count,  # Number of chunks to return from the search
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )

            logger.debug("Search response: %s %s", response.text, response.status_code)

            response.raise_for_status()

        searches = Searches(**response.json())

        return RAGWebResults(
            data=[
                RAGWebResult(
                    url=result.chunk.metadata["document_name"],
                    content=result.chunk.content,
                    score=result.score,
                )
                for result in searches.data
            ],
            usage=RAGWebUsage(
                prompt_tokens=searches.usage.prompt_tokens,
                completion_tokens=searches.usage.completion_tokens,
            ),
        )
