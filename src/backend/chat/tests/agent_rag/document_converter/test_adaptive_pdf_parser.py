"""Tests for AdaptivePdfParser and AdaptiveParserMixin."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pypdf import PdfReader

from chat.agent_rag.document_converter.odt import OdtParsingError
from chat.agent_rag.document_converter.parser import (
    METHOD_OCR,
    METHOD_TEXT_EXTRACTION,
    AdaptivePdfParser,
    MistralOcr,
    analyze_pdf,
    use_fallback_ocr,
)
from chat.model_health import set_model_health

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(name="text_pdf_1_page")
def provide_text_pdf_1_page():
    """Load a 1 page PDF with extractable text."""
    return (FIXTURES_DIR / "text_pdf_1_page.pdf").read_bytes()


@pytest.fixture(name="text_pdf_10_pages")
def provide_text_pdf_10_pages():
    """Load a 10-page PDF with extractable text (~300 chars per page)."""
    return (FIXTURES_DIR / "text_10_pages.pdf").read_bytes()


@pytest.fixture(name="mixed_pdf_10_pages")
def provide_mixed_pdf_10_pages():
    """Load a 10-page PDF with 2 pages of text and 8 blank pages."""
    return (FIXTURES_DIR / "mixed_10_pages.pdf").read_bytes()


@pytest.fixture(name="sample_odt")
def provide_sample_odt():
    """Load an ODT document."""
    return (FIXTURES_DIR / "sample.odt").read_bytes()


MIN_AVG_CHARS_FOR_TEXT_EXTRACTION = 200
OCR_RETRY_DELAY = 1
OCR_MAX_RETRIES = 3


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Mock Django settings for OCR configuration."""
    settings.MIN_AVG_CHARS_FOR_TEXT_EXTRACTION = MIN_AVG_CHARS_FOR_TEXT_EXTRACTION
    settings.OCR_HRID = "test-ocr-hrid"
    settings.OCR_MODEL = "test-ocr-model"
    settings.OCR_TIMEOUT = 60
    settings.OCR_MAX_RETRIES = OCR_MAX_RETRIES
    settings.OCR_RETRY_DELAY = OCR_RETRY_DELAY
    settings.OCR_FALLBACK_HRID = ""
    settings.LLM_CONFIGURATIONS = {
        "test-ocr-hrid": MagicMock(
            model_name="test-ocr-model",
            provider=MagicMock(
                hrid="albert",
                base_url="https://ocr.example.com",
                api_key="test-api-key",
            ),
        ),
        "test-ocr-fallback-hrid": MagicMock(
            model_name="test-ocr-fallback-model",
            provider=MagicMock(
                hrid="albert",
                base_url="https://fallback-ocr.example.com",
                api_key="test-fallback-api-key",
            ),
        ),
    }
    return settings


def test_analyze_pdf_returns_correct_structure(text_pdf_10_pages):
    """analyze_pdf should return dict with expected keys."""
    result = analyze_pdf(text_pdf_10_pages)

    assert "total_pages" in result
    assert "pages_with_text" in result
    assert "avg_chars_per_page" in result
    assert "text_coverage" in result
    assert "recommended_method" in result


def test_analyze_pdf_with_text_recommends_extraction(text_pdf_1_page):
    """PDF with sufficient text should recommend text extraction."""
    result = analyze_pdf(text_pdf_1_page)

    assert result["total_pages"] == 1
    assert result["pages_with_text"] == 1
    assert result["text_coverage"] == pytest.approx(1.0)
    assert result["avg_chars_per_page"] > MIN_AVG_CHARS_FOR_TEXT_EXTRACTION
    assert result["recommended_method"] == METHOD_TEXT_EXTRACTION


def test_analyze_multi_page_pdf_with_text_recommends_extraction(text_pdf_10_pages):
    """PDF with sufficient text should recommend text extraction."""
    result = analyze_pdf(text_pdf_10_pages)

    assert result["total_pages"] == 10
    assert result["pages_with_text"] == 10
    assert result["text_coverage"] == pytest.approx(1.0)
    assert result["avg_chars_per_page"] > MIN_AVG_CHARS_FOR_TEXT_EXTRACTION
    assert result["recommended_method"] == METHOD_TEXT_EXTRACTION


def test_analyze_pdf_mixed_content_recommends_ocr(mixed_pdf_10_pages):
    """PDF with low text coverage should recommend OCR."""
    result = analyze_pdf(mixed_pdf_10_pages)

    assert result["total_pages"] == 10
    assert result["pages_with_text"] == 2
    assert result["text_coverage"] == pytest.approx(0.2)
    assert result["recommended_method"] == METHOD_OCR


def test_extract_page_batch_single_page(text_pdf_10_pages):
    """Should extract a single page correctly."""
    reader = PdfReader(BytesIO(text_pdf_10_pages))

    result = MistralOcr().extract_page_batch(reader, 0, 1)

    result_reader = PdfReader(BytesIO(result))
    assert len(result_reader.pages) == 1


def test_extract_page_batch_multiple_pages(text_pdf_10_pages):
    """Should extract multiple pages correctly."""
    reader = PdfReader(BytesIO(text_pdf_10_pages))

    result = MistralOcr().extract_page_batch(reader, 2, 7)

    result_reader = PdfReader(BytesIO(result))
    assert len(result_reader.pages) == 5


def test_extract_page_batch_last_batch(text_pdf_10_pages):
    """Should handle last batch with fewer pages."""
    reader = PdfReader(BytesIO(text_pdf_10_pages))

    result = MistralOcr().extract_page_batch(reader, 7, 10)

    result_reader = PdfReader(BytesIO(result))
    assert len(result_reader.pages) == 3


def test_ocr_page_batch_success(text_pdf_1_page):
    """Should return markdown content on successful OCR."""
    client = MistralOcr()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "pages": [
                {"markdown": "# Page 1 content"},
            ]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = client.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

        assert result == ["# Page 1 content"]
        mock_post.assert_called_once()


def test_ocr_page_batch_retry_on_timeout(text_pdf_1_page):
    """Should retry on timeout with static delay."""
    client = MistralOcr()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep") as mock_sleep:
            mock_post.side_effect = [
                httpx.TimeoutException("Connection timed out"),
                MagicMock(
                    json=MagicMock(return_value={"pages": [{"markdown": "# Content"}]}),
                    raise_for_status=MagicMock(),
                ),
            ]

            result = client.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

            assert result == ["# Content"]
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once_with(OCR_RETRY_DELAY)


def test_ocr_page_batch_fails_after_max_retries(text_pdf_1_page):
    """Should raise exception after max retries exceeded."""
    client = MistralOcr()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            mock_post.side_effect = httpx.TimeoutException("Connection timed out")

            with pytest.raises(httpx.TimeoutException):
                client.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

            assert mock_post.call_count == OCR_MAX_RETRIES


def test_ocr_page_batch_retry_on_request_exception(text_pdf_1_page):
    """Should retry on general request exceptions."""
    client = MistralOcr()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            mock_post.side_effect = [
                httpx.HTTPError("Network error"),
                httpx.HTTPError("Network error"),
                MagicMock(
                    json=MagicMock(return_value={"pages": [{"markdown": "# Content"}]}),
                    raise_for_status=MagicMock(),
                ),
            ]

            result = client.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

            assert result == ["# Content"]
            assert mock_post.call_count == 3


def test_parse_pdf_with_ocr_single_batch(text_pdf_10_pages):
    """Should process PDF in single batch when pages <= batch size."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "pages": [{"markdown": f"Page {i}"} for i in range(1, 11)]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = parser.parse_pdf_document_with_ocr("test.pdf", text_pdf_10_pages)

        assert "Page 1" in result
        assert "Page 10" in result
        mock_post.assert_called_once()


def test_parse_pdf_with_ocr_multiple_batches(text_pdf_10_pages, settings):
    """Should process PDF in multiple batches when pages > batch size."""
    settings.OCR_BATCH_PAGES = 4  # Force multiple batches
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value.json.side_effect = [
            {"pages": [{"markdown": f"Page {i}"} for i in range(1, 5)]},
            {"pages": [{"markdown": f"Page {i}"} for i in range(5, 9)]},
            {"pages": [{"markdown": f"Page {i}"} for i in range(9, 11)]},
        ]
        mock_post.return_value.raise_for_status = MagicMock()

        result = parser.parse_pdf_document_with_ocr("test.pdf", text_pdf_10_pages)

        assert mock_post.call_count == 3
        assert "Page 1" in result
        assert "Page 10" in result


def test_parse_pdf_with_ocr_batch_failure_aborts_document(text_pdf_10_pages, settings):
    """Should fail the whole document when one batch exhausts its retries."""
    settings.OCR_BATCH_PAGES = 4  # Force multiple batches
    parser = AdaptivePdfParser()

    success_response = MagicMock()
    success_response.json.return_value = {"pages": [{"markdown": f"Page {i}"} for i in range(1, 5)]}
    success_response.raise_for_status = MagicMock()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            # First batch succeeds, the second exhausts its retries
            mock_post.side_effect = [
                success_response,
                httpx.TimeoutException("OCR failed"),
                httpx.TimeoutException("OCR failed"),
                httpx.TimeoutException("OCR failed"),
            ]

            with pytest.raises(httpx.TimeoutException):
                parser.parse_pdf_document_with_ocr("test.pdf", text_pdf_10_pages)

            # Aborted on the failed batch: the third batch is never sent.
            assert mock_post.call_count == 4


def test_parse_document_pdf_routed_correctly(text_pdf_1_page):
    """Should route PDF content type to PDF parser."""
    parser = AdaptivePdfParser()

    with patch.object(parser, "parse_pdf_document", return_value="pdf content") as mock_parse:
        result = parser.parse_document("test.pdf", "application/pdf", text_pdf_1_page)

        assert result == "pdf content"
        mock_parse.assert_called_once_with(
            name="test.pdf",
            content_type="application/pdf",
            content=text_pdf_1_page,
        )


def test_text_pdf_routed_to_text_extraction(text_pdf_10_pages):
    """Text-rich PDF should be routed to extract_text_from_pdf, not OCR."""
    parser = AdaptivePdfParser()

    with (
        patch.object(parser, "extract_text_from_pdf", return_value="extracted") as mock_extract,
        patch.object(parser, "parse_pdf_document_with_ocr") as mock_ocr,
    ):
        result = parser.parse_pdf_document(
            name="test.pdf", content_type="application/pdf", content=text_pdf_10_pages
        )

        assert result == "extracted"
        mock_extract.assert_called_once_with(
            name="test.pdf", content_type="application/pdf", content=text_pdf_10_pages
        )
        mock_ocr.assert_not_called()


def test_mixed_pdf_routed_to_ocr(mixed_pdf_10_pages):
    """PDF with low text coverage should be routed to OCR, not text extraction."""
    parser = AdaptivePdfParser()

    with (
        patch.object(parser, "extract_text_from_pdf") as mock_extract,
        patch.object(parser, "parse_pdf_document_with_ocr", return_value="ocr result") as mock_ocr,
    ):
        result = parser.parse_pdf_document(
            name="test.pdf", content_type="application/pdf", content=mixed_pdf_10_pages
        )

        assert result == "ocr result"
        mock_ocr.assert_called_once_with(name="test.pdf", content=mixed_pdf_10_pages)
        mock_extract.assert_not_called()


def test_parse_document_pdf(text_pdf_1_page):
    """Should route PDF content type to PDF parser."""
    parser = AdaptivePdfParser()

    result = parser.parse_document("test.pdf", "application/pdf", text_pdf_1_page)

    assert result == (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
        "incididunt ut\nlabore et dolore magna aliqua. Ut enim ad minim veniam, "
        "quis nostrud exercitation ullamco\nlaboris nisi ut aliquip ex ea commodo consequat. "
        "Duis aute irure dolor in reprehenderit in\nvoluptate velit esse cillum dolore eu fugiat "
        "nulla pariatur. Excepteur sint occaecat cupidatat non\nproident, sunt in culpa qui "
        "oﬃcia deserunt mollit anim id est laborum.\n\nLorem ipsum dolor sit amet, consectetur "
        "adipiscing elit, sed do eiusmod tempor incididunt ut\nlabore et dolore magna aliqua. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco\nlaboris nisi ut aliquip "
        "ex ea commodo consequat. Duis aute irure dolor in reprehenderit in\nvoluptate velit "
        "esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non"
        "\nproident, sunt in culpa qui oﬃcia deserunt mollit anim id est laborum.\n\n"
    )


def test_parse_document_non_pdf_uses_document_converter():
    """Should route non-PDF content to DocumentConverter."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.DocumentConverter") as mock_converter:
        mock_converter.return_value.convert_raw.return_value = "docx content"

        result = parser.parse_document("test.docx", "application/vnd.openxmlformats", b"content")

        assert result == "docx content"
        mock_converter.return_value.convert_raw.assert_called_once()


EXPECTED_MD_FROM_ODT = (
    "# Document Title\n\n## Introduction\n\nThis is a normal paragraph with "
    "**bold text**, \\\n_italic text_, and \\\n***bold italic text***."
    "\\\n\n\nThis has ~~strikethrough~~ and \\\n`inline code`.\\\n\n\n"
    "Visit [Example Site](https://example.com) for more info.\\\n\n\n"
    "## Features\n\n -  Fast parsing\n -  Clean output\n -  "
    "Django integration\n -  LLM\\-ready markdown\n\n"
    "### Nested List\n\n -  Parent item\n    -  Child A"
    "\n    -  Child B\n -  Another parent\n\n## Data Table\n\n"
    "| Name  | Age | City   |\n|-------|-----|--------|\n"
    "| Alice | 30  | Paris  |\n| Bob   | 25  | London |"
    "\n\n\n## Conclusion\n\nThis document tests "
    "the ODT to Markdown conversion pipeline.\n"
)


def test_parse_odt(sample_odt):
    """Should extract odt document correctly."""
    parser = AdaptivePdfParser()

    result = parser.parse_document(
        "sample.odt", "application/vnd.oasis.opendocument.text", sample_odt
    )

    assert result == EXPECTED_MD_FROM_ODT


def test_parse_document_odt_routed_correctly(sample_odt):
    """Should route ODT content type to ODT parser."""
    parser = AdaptivePdfParser()

    with patch.object(parser, "parse_odt_document", return_value="odt content") as mock_parse:
        result = parser.parse_document(
            "sample.odt", "application/vnd.oasis.opendocument.text", sample_odt
        )

        assert result == "odt content"
        mock_parse.assert_called_once_with(content=sample_odt)


def test_parse_odt_corrupt_input():
    """Should raise OdtParsingError on corrupt input."""
    parser = AdaptivePdfParser()

    with pytest.raises(OdtParsingError):
        parser.parse_document("corrupt.odt", "application/vnd.oasis.opendocument.text", b"garbage")


def test_parse_odt_empty_input():
    """Should raise OdtParsingError on empty input."""
    parser = AdaptivePdfParser()

    with pytest.raises(OdtParsingError):
        parser.parse_document("empty.odt", "application/vnd.oasis.opendocument.text", b"")


@pytest.fixture(name="fallback_configured")
def provide_fallback_configured(settings):
    """Point the OCR fallback at a configured HRID/model pair."""
    settings.OCR_FALLBACK_HRID = "test-ocr-fallback-hrid"
    return settings


@pytest.mark.parametrize(
    "main_status,fallback_status,expected",
    [
        ("green", "green", False),
        ("green", "red", False),
        ("yellow", "green", True),
        ("red", "green", True),
        ("red", "yellow", False),
        ("red", "red", False),
        ("red", None, False),
        # Health data missing for the main model is not a green light either.
        (None, "green", True),
        (None, None, False),
    ],
)
def test_use_fallback_ocr_follows_model_health(
    clear_cache, fallback_configured, main_status, fallback_status, expected
):  # pylint: disable=unused-argument
    """The fallback only takes over when it is green and the main model is not."""
    if main_status:
        set_model_health("albert", "test-ocr-model", main_status)
    if fallback_status:
        set_model_health("albert", "test-ocr-fallback-model", fallback_status)

    assert use_fallback_ocr() is expected


def test_use_fallback_ocr_is_off_when_not_configured(clear_cache):  # pylint: disable=unused-argument
    """An unconfigured fallback never takes over, however bad the main model is."""
    set_model_health("albert", "test-ocr-model", "red")

    assert use_fallback_ocr() is False


def test_parse_pdf_with_ocr_routes_to_the_fallback(
    clear_cache, fallback_configured, text_pdf_10_pages
):  # pylint: disable=unused-argument
    """A degraded main model sends the document to the LightOn fallback."""
    set_model_health("albert", "test-ocr-model", "red")
    set_model_health("albert", "test-ocr-fallback-model", "green")
    parser = AdaptivePdfParser()

    with patch(
        "chat.agent_rag.document_converter.parser.LightOnOcr", autospec=True
    ) as mock_lighton:
        mock_lighton.return_value.parse_pdf_document.return_value = "fallback markdown"

        result = parser.parse_pdf_document_with_ocr("test.pdf", text_pdf_10_pages)

        assert result == "fallback markdown"
        mock_lighton.return_value.parse_pdf_document.assert_called_once_with(
            name="test.pdf", content=text_pdf_10_pages
        )


def test_parse_pdf_with_ocr_stays_on_mistral_when_the_fallback_is_down(
    clear_cache, fallback_configured, text_pdf_10_pages
):  # pylint: disable=unused-argument
    """Both models degraded: the document goes to Mistral OCR and fails there."""
    set_model_health("albert", "test-ocr-model", "red")
    set_model_health("albert", "test-ocr-fallback-model", "red")
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "pages": [{"markdown": f"Page {i}"} for i in range(1, 11)]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = parser.parse_pdf_document_with_ocr("test.pdf", text_pdf_10_pages)

        assert "Page 1" in result
        mock_post.assert_called_once()
