"""
Unit tests for the DoclingParser.
"""
from chat.agent_rag.document_converter.parser import DoclingParser


def test_document_converter():
    """Test that the DocumentConverter calls the underlying MarkItDown converter."""
    file_name = "test"
    content_type = "application/pdf"
    file_path = "src/backend/chat/tests/data/test.pdf"
    parser = DoclingParser()

    with open(file_path, "rb") as file:
        content = file.read()
        result = parser.parse_document(name= file_name, content_type= content_type, content= content)

    assert "Document PDF test" in result
