"""
Unit tests for the DocumentConverter.

Only for coverage as the DocumentConverter is a simple wrapper around MarkItDown.
"""

from io import BytesIO

from docling.document_converter import DocumentConverter
from docling_core.types.io import DocumentStream


def main():
    """Test that the DocumentConverter calls the underlying MarkItDown converter."""
    file_path = "test.pdf"
    converter = DocumentConverter()

    # Convert from file content instead of file path
    with open(file_path, "rb") as file:
        content = file.read()
        stream = DocumentStream(name="test.pdf", stream=BytesIO(content))
        result = converter.convert(stream)
        markdown = result.document.export_to_markdown()

    assert markdown == "Document PDF test"


if __name__ == "__main__":
    main()
