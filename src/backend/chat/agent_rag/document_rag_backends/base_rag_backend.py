"""Implementation of the Albert API for RAG document search."""

import logging
from contextlib import contextmanager
from io import BytesIO
from typing import Optional

from chat.agent_rag.constants import RAGWebResults

logger = logging.getLogger(__name__)


class BaseRagBackend:
    """Base class for RAG backends."""

    def __init__(self, collection_id: Optional[str] = None):
        """Backend settings."""
        self.collection_id = collection_id
        self._default_collection_description = "Temporary collection for RAG document search"

    def create_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        raise NotImplementedError("Must be implemented in subclass.")

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
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
        """
        raise NotImplementedError("Must be implemented in subclass.")

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

    def search(self, query) -> RAGWebResults:
        """
        Search the collection for the given query.
        """
        raise NotImplementedError("Must be implemented in subclass.")

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
