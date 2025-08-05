"""Document Converter using MarkItDown"""

from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Union

from markitdown import MarkItDown


class DocumentConverter:
    """Simple document converter that uses MarkItDown to convert documents to Markdown format."""

    def __init__(self):
        """Initialize the DocumentConverter with MarkItDown."""
        self.converter = MarkItDown(enable_plugins=False)

    def convert_raw(  # pylint: disable=unused-argument
        self,
        *,
        name: str,
        content_type: str,
        content: BytesIO,
    ) -> str:
        """
        Convert a document to Markdown format.
        The name, content_type, and content parameters comes from the user input
        (vercel SDK Attachment, or BinaryContent).

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (BytesIO): The content of the document as a BytesIO stream.
        """
        return self._convert(content)

    def _convert(self, document: Union[Path, str, BinaryIO]) -> str:
        """
        Convert the given document using the underlying DocumentConverter.
        """
        conversion = self.converter.convert(document)
        document_markdown = conversion.text_content
        return document_markdown
