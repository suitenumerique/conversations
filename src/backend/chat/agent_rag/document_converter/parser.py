"""Document parsers for RAG backends."""

import logging
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings

import requests

from chat.agent_rag.document_converter.markitdown import DocumentConverter

logger = logging.getLogger(__name__)


class BaseParser:
    """Base class for document parsers."""

    def parse_document(self, name: str, content_type: str, content: BytesIO) -> str:
        """
        Parse the document and prepare it for the search operation.
        This method should handle the logic to convert the document
        into a format suitable for storage.

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (BytesIO): The content of the document as a BytesIO stream.

        Returns:
            str: The document content in Markdown format.
        """
        raise NotImplementedError("Must be implemented in subclass.")


class AlbertParser(BaseParser):
    """Document parser using Albert API for PDFs and DocumentConverter for other formats."""

    endpoint = urljoin(settings.ALBERT_API_URL, "/v1/parse-beta")

    def parse_pdf_document(self, name: str, content_type: str, content: BytesIO) -> str:
        """Parse PDF document using Albert API."""
        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
            },
            files={
                "file": (name, content, content_type),
                "output_format": (None, "markdown"),
            },
            timeout=settings.ALBERT_API_PARSE_TIMEOUT,
        )
        response.raise_for_status()

        return "\n\n".join(
            document_page["content"] for document_page in response.json().get("data", [])
        )

    def parse_document(self, name: str, content_type: str, content: BytesIO) -> str:
        """Parse document based on content type."""
        if content_type == "application/pdf":
            return self.parse_pdf_document(name=name, content_type=content_type, content=content)
        return DocumentConverter().convert_raw(
            name=name, content_type=content_type, content=content
        )
