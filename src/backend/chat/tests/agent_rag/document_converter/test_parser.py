"""Tests for BaseParser and AlbertParser."""

from pathlib import Path
from unittest.mock import patch

import pytest
import responses

from chat.agent_rag.document_converter.parser import (
    AlbertParser,
    BaseParser,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
ALBERT_API_KEY = "test-key"
ALBERT_PARSE_ENDPOINT = f"{ALBERT_API_URL}/v1/parse-beta"


@pytest.fixture(name="sample_odt")
def provide_sample_odt():
    """Load an ODT document."""
    return (FIXTURES_DIR / "sample.odt").read_bytes()


@pytest.fixture(autouse=True)
def albert_settings(settings):
    """Configure Django settings for AlbertParser."""
    settings.ALBERT_API_URL = ALBERT_API_URL
    settings.ALBERT_API_KEY = ALBERT_API_KEY
    settings.ALBERT_API_PARSE_TIMEOUT = 30
    # AlbertParser.endpoint is resolved at import time from settings.ALBERT_API_URL,
    # so override it explicitly to use the test constant.
    AlbertParser.endpoint = ALBERT_PARSE_ENDPOINT
    return settings


def test_base_parser_cannot_be_instantiated():
    """BaseParser is abstract and should not be instantiable."""
    with pytest.raises(TypeError, match="abstract"):
        BaseParser()  # pylint: disable=abstract-class-instantiated


@responses.activate
def test_albert_parser_pdf_success():
    """AlbertParser should call Albert API and join page contents."""
    responses.add(
        responses.POST,
        ALBERT_PARSE_ENDPOINT,
        json={
            "data": [
                {"content": "# Page 1"},
                {"content": "## Page 2"},
                {"content": "End."},
            ]
        },
        status=200,
    )

    parser = AlbertParser()

    result = parser.parse_document("report.pdf", "application/pdf", b"pdf-bytes")

    assert result == "# Page 1\n\n## Page 2\n\nEnd."
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == ALBERT_PARSE_ENDPOINT


@responses.activate
def test_albert_parser_pdf_http_error():
    """AlbertParser should propagate HTTP errors from Albert API."""
    responses.add(
        responses.POST,
        ALBERT_PARSE_ENDPOINT,
        json={"error": "Internal Server Error"},
        status=500,
    )

    parser = AlbertParser()

    with pytest.raises(Exception, match="500"):
        parser.parse_document("report.pdf", "application/pdf", b"pdf-bytes")


def test_albert_parser_odt_uses_mixin(sample_odt):
    """AlbertParser should parse ODT via OdtParserMixin (real parsing, no mocks)."""
    parser = AlbertParser()
    result = parser.parse_document(
        "sample.odt", "application/vnd.oasis.opendocument.text", sample_odt
    )

    assert "Document Title" in result
    assert "Django integration" in result


def test_albert_parser_other_format_uses_document_converter():
    """AlbertParser should fall back to DocumentConverter for unknown formats."""
    parser = AlbertParser()

    with patch("chat.agent_rag.document_converter.parser.DocumentConverter") as mock_converter:
        mock_converter.return_value.convert_raw.return_value = "converted text"

        result = parser.parse_document("notes.txt", "text/plain", b"hello world")

        assert result == "converted text"
        mock_converter.return_value.convert_raw.assert_called_once_with(
            name="notes.txt", content_type="text/plain", content=b"hello world"
        )
