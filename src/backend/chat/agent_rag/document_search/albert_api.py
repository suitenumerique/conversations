"""Implementation of the Albert API for RAG document search."""

import json
import logging
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings

import requests

from chat.agent_rag.albert_api_constants import Searches
from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_converter.parser import DoclingParser
from chat.models import ChatConversation

logger = logging.getLogger(__name__)


class AlbertRagDocumentSearch:
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

    def __init__(self, conversation: ChatConversation):
        # Initialize any necessary parameters or configurations here
        self._base_url = settings.ALBERT_API_URL
        self._headers = {
            "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
        }
        self._collections_endpoint = urljoin(self._base_url, "/v1/collections")
        self._documents_endpoint = urljoin(self._base_url, "/v1/documents")
        self._pdf_parser_endpoint = urljoin(self._base_url, "/v1/parse-beta")
        self._search_endpoint = urljoin(self._base_url, "/v1/search")

        self.conversation = conversation

    @property
    def _albert_collection_id(self):
        """
        Generate the collection name based on the conversation ID.
        This is used to create or retrieve a collection for the search operation.
        """
        return f"conversation-{self.conversation.pk}"

    @property
    def collection_id(self) -> int:
        """
        Get the collection ID for the current conversation.

        Might be created later by self._create_collection() if it does not exist.
        """
        return int(self.conversation.collection_id) if self.conversation.collection_id else None

    def _create_collection(self) -> bool:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        response = requests.post(
            self._collections_endpoint,
            headers=self._headers,
            json={
                "name": self._albert_collection_id,
                "description": "Temporary collection for RAG document search",
                "visibility": "private",
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()
        self.conversation.collection_id = str(response.json()["id"])
        return True

    def _store_document(self, name: str, content: str):
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.

        Args:
            content (str): The content of the document in Markdown format.
        """
        if not self.collection_id and not self._create_collection():
            raise RuntimeError("Failed to create or retrieve the collection.")

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

    def parse_and_store_document(self, name: str, content_type: str, content: bytes):
        """
        Parse the document and store it in the Albert collection.

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (BytesIO): The content of the document as a BytesIO stream.
        """
        document_content = DoclingParser().parse_document(
            name=name, content_type=content_type, content=content
        )
        self._store_document(name, document_content)
        return document_content

    def search(self, query, results_count: int = 4) -> RAGWebResults:
        """
        Perform a search using the Albert API based on the provided query.

        :param query: The search query string.
        :param results_count: The number of results to return.
        :return: Search results from the Albert API.
        """
        response = requests.post(
            urljoin(self._base_url, self._search_endpoint),
            headers=self._headers,
            json={
                "collections": [self.collection_id],
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
