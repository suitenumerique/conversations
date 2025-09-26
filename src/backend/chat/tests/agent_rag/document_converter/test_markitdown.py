"""
Unit tests for the DocumentConverter.

Only for coverage as the DocumentConverter is a simple wrapper around MarkItDown.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

from chat.agent_rag.document_converter.markitdown import DocumentConverter


@patch("chat.agent_rag.document_converter.markitdown.MarkItDown")
def test_document_converter(mock_markitdown: MagicMock):
    """Test that the DocumentConverter calls the underlying MarkItDown converter."""
    mock_conversion = MagicMock()
    mock_conversion.text_content = "converted text"
    mock_markitdown.return_value.convert_stream.return_value = mock_conversion

    converter = DocumentConverter()

    result = converter.convert_raw(
        name="test.pdf",
        content_type="application/pdf",
        content=b"test content",
    )

    assert result == "converted text"
    converter.converter.convert_stream.assert_called_once()  # pylint: disable=no-member
    args, kwargs = converter.converter.convert_stream.call_args  # pylint: disable=no-member
    assert isinstance(args[0], BytesIO)
    assert kwargs["file_extension"] == ".pdf"
