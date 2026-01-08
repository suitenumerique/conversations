"""
Unit tests for the DocumentConverter.

Only for coverage as the DocumentConverter is a simple wrapper around MarkItDown.
"""

from io import BytesIO

from chat.agent_rag.document_converter.markitdown import DocumentConverter


def test_document_converter():
    """Test that the DocumentConverter calls the underlying MarkItDown converter."""
    file_path = "src/backend/chat/tests/data/test.pdf"
    converter = DocumentConverter()

    with open(file_path, "rb") as file:
        content = file.read()
        result = converter.convert_raw(
            name="test.pdf",
            content_type="application/pdf",
            content=content,
        )

    assert result == "Document PDF test\n\n"
