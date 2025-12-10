"""Implementation of the Albert API for RAG document search."""

import logging
from contextlib import asynccontextmanager, contextmanager
from io import BytesIO
from typing import List, Optional

from asgiref.sync import sync_to_async

from chat.agent_rag.constants import RAGWebResults

logger = logging.getLogger(__name__)


class BaseRagBackend:
    """Base class for RAG backends."""

    def __init__(
        self,
        collection_id: Optional[str] = None,
        read_only_collection_id: Optional[List[str]] = None,
    ):
        """
        Backend settings.

        Collection ID is required for RAG operations, where you want to manage the collection
        lifecycle (create/delete).
        Read-only collection IDs can be used to access existing collections
        without managing their lifecycle.

        Collection ID and read-only collection IDs are separated in the implementation to prevent
        unwanted actions.

        Args:
            collection_id (Optional[str]): The collection ID for managing the collection lifecycle.
            read_only_collection_id (Optional[List[str]]): List of read-only collection IDs.
        """
        self.collection_id = collection_id
        self.read_only_collection_id = read_only_collection_id or []
        self._default_collection_description = "Temporary collection for RAG document search"

    def get_all_collection_ids(self) -> List[str]:
        """
        Get all collection IDs, including the main collection ID and read-only collection IDs.

        Returns:
            List[str]: List of all collection IDs.
        Raises:
            RuntimeError: If neither collection_id nor read_only_collection_id is provided.
        """
        if not self.collection_id and not self.read_only_collection_id:
            raise RuntimeError("The RAG backend requires collection_id or read_only_collection_id")

        collection_ids = []
        if self.collection_id:
            collection_ids.append(int(self.collection_id))
        if self.read_only_collection_id:
            collection_ids.extend(
                [int(collection_id) for collection_id in self.read_only_collection_id]
            )
        return collection_ids

    def create_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        raise NotImplementedError("Must be implemented in subclass.")

    async def acreate_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        return await sync_to_async(self.create_collection)(name=name, description=description)

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
        raise NotImplementedError("Must be implemented in subclass.")

    def store_document(self, name: str, content: str) -> None:
        """
        Store the document content in the collection.
        This method should handle the logic to send the document content to the API.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
        """
        raise NotImplementedError("Must be implemented in subclass.")

    async def astore_document(self, name: str, content: str) -> None:
        """
        Store the document content in the collection.
        This method should handle the logic to send the document content to the API.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
        """
        return await sync_to_async(self.store_document)(name=name, content=content)

    def parse_and_store_document(self, name: str, content_type: str, content: BytesIO) -> str:
        """
        Parse the document and store it in the Albert collection.

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (BytesIO): The content of the document as a BytesIO stream.
        """
        if not self.collection_id:
            raise RuntimeError("The RAG backend requires collection_id")

        document_content = self.parse_document(name, content_type, content)
        self.store_document(name, document_content)
        return document_content

    def delete_collection(self) -> None:
        """
        Delete the collection.
        This method should handle the logic to delete the collection from the backend.
        """
        raise NotImplementedError("Must be implemented in subclass.")

    async def adelete_collection(self) -> None:
        """
        Delete the collection.
        This method should handle the logic to delete the collection from the backend.
        """
        return await sync_to_async(self.delete_collection)()

    def search(self, query, results_count: int = 4) -> RAGWebResults:
        """
        Search the collection for the given query.
        """
        raise NotImplementedError("Must be implemented in subclass.")

    async def asearch(self, query, results_count: int = 4) -> RAGWebResults:
        """
        Search the collection for the given query.
        """
        return await sync_to_async(self.search)(query=query, results_count=results_count)

    @classmethod
    @contextmanager
    def temporary_collection(cls, name: str, description: Optional[str] = None):
        """Context manager for RAG backend with temporary collections."""
        backend = cls()

        backend.create_collection(name=name, description=description)
        try:
            yield backend
        finally:
            backend.delete_collection()

    @classmethod
    @asynccontextmanager
    async def temporary_collection_async(cls, name: str, description: Optional[str] = None):
        """Context manager for RAG backend with temporary collections."""
        backend = cls()

        await backend.acreate_collection(name=name, description=description)
        try:
            yield backend
        finally:
            await backend.adelete_collection()
