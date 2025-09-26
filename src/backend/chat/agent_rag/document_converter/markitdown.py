"""Document Converter using MarkItDown"""

import os.path
from io import BytesIO

from markitdown import MarkItDown


class DocumentConverter:
    """Simple document converter that uses MarkItDown to convert documents to Markdown format."""

    def __init__(self):
        """Initialize the DocumentConverter with MarkItDown."""
        self.converter = MarkItDown()

    def convert_raw(  # pylint: disable=unused-argument
        self,
        *,
        name: str,
        content_type: str,
        content: bytes,
    ) -> str:
        """
        Convert a document to Markdown format.
        The name, content_type, and content parameters comes from the user input
        (vercel SDK Attachment, or BinaryContent).

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (bytes): The content of the document as bytes.
        """
        return self._convert(BytesIO(content), file_extension=os.path.splitext(name)[1])

    def _convert(self, document: BytesIO, file_extension: str) -> str:
        """
        Convert the given document using the underlying DocumentConverter.
        """
        conversion = self.converter.convert_stream(
            document, file_extension=file_extension or ".txt"
        )
        document_markdown = conversion.text_content
        return document_markdown
