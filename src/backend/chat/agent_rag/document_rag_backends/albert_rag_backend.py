"""Implementation of the Albert API for RAG document search."""

import json
import logging
from io import BytesIO
from typing import List, Optional
from urllib.parse import urljoin

from django.conf import settings

import requests

from chat.agent_rag.albert_api_constants import Searches
from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_converter.markitdown import DocumentConverter
from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend

logger = logging.getLogger(__name__)


class AlbertRagBackend(BaseRagBackend):  # pylint: disable=too-many-instance-attributes
    """
    This class is a placeholder for the Albert API implementation.
    It is designed to be used with the RAG (Retrieval-Augmented Generation) document search system.

    It provides methods to:
    - Create a collection for the search operation.
    - Parse documents and convert them to Markdown format:
       + Handle PDF parsing using the Albert API.
       + Use the DocumentConverter (markitdown) for other formats.
    - Store parsed documents in the Albert collection.
    - Perform a search operation using the Albert API.
    """

    def __init__(self, collection_id: Optional[str] = None):
        # Initialize any necessary parameters or configurations here
        super().__init__(collection_id)
        self._base_url = settings.ALBERT_API_URL
        self._headers = {
            "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
        }
        self._collections_endpoint = urljoin(self._base_url, "/v1/collections")
        self._documents_endpoint = urljoin(self._base_url, "/v1/documents")
        self._pdf_parser_endpoint = urljoin(self._base_url, "/v1/parse-beta")
        self._search_endpoint = urljoin(self._base_url, "/v1/search")

        self._default_collection_description = "Temporary collection for RAG document search"

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

    def delete_collection(self) -> None:
        """
        Delete the current collection
        """
        response = requests.delete(
            urljoin(f"{self._collections_endpoint}/", self.collection_id),
            headers=self._headers,
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

    def parse_pdf_document(self, name: str, content_type: str, content: BytesIO) -> str:
        """
        Parse the PDF document content and return the text content.
        This method should handle the logic to convert the PDF into
        a format suitable for the Albert API.
        """
        response = requests.post(
            self._pdf_parser_endpoint,
            headers=self._headers,
            files={
                "file": (
                    name,
                    content,
                    content_type,
                ),  # Use the name as the filename in the request
                "output_format": (None, "markdown"),  # Specify the output format as Markdown,
            },
            timeout=settings.ALBERT_API_PARSE_TIMEOUT,
        )
        response.raise_for_status()

        return "\n\n".join(
            document_page["content"] for document_page in response.json().get("data", [])
        )

    def parse_document(self, name: str, content_type: str, content: BytesIO):
        """
        Parse the document and prepare it for the search operation.
        This method should handle the logic to convert the document
        into a format suitable for the Albert API.

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (BytesIO): The content of the document as a BytesIO stream.

        Returns:
            str: The document content in Markdown format.
        """
        # Implement the parsing logic here
        if content_type == "application/pdf":
            # Handle PDF parsing
            markdown_content = self.parse_pdf_document(
                name=name, content_type=content_type, content=content
            )
        else:
            markdown_content = DocumentConverter().convert_raw(
                name=name, content_type=content_type, content=content
            )

        return markdown_content

    def store_document(self, name: str, content: str) -> None:
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
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

    def search(self, query, results_count: int = 4, collections: Optional[List[int]] = None) -> RAGWebResults:
        """
        Perform a search using the Albert API based on the provided query.

        Args:
            query (str): The search query.
            results_count (int): The number of results to return.
            collections (Optional[List[int]]): List of collection IDs to search in.
                                             If None, uses the current collection_id.

        Returns:
            RAGWebResults: The search results.
        """
        # Use provided collections or fall back to current collection_id
        if collections is not None:
            collection_list = collections
        else:
            collection_list = [int(self.collection_id)]

        response = requests.post(
            urljoin(self._base_url, self._search_endpoint),
            headers=self._headers,
            json={
                "collections": collection_list,
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
                    metadata=result.chunk.metadata,
                )
                for result in searches.data
            ],
            usage=RAGWebUsage(
                prompt_tokens=searches.usage.prompt_tokens,
                completion_tokens=searches.usage.completion_tokens,
            ),
        )
