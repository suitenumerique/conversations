"""Tests for AdaptivePdfParser and AdaptiveParserMixin."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from pypdf import PdfReader

from chat.agent_rag.document_converter.parser import (
    METHOD_OCR,
    METHOD_TEXT_EXTRACTION,
    AdaptivePdfParser,
    analyze_pdf,
)

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


MIN_AVG_CHARS_FOR_TEXT_EXTRACTION = 200
OCR_RETRY_DELAY = 1
OCR_MAX_RETRIES = 3


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Mock Django settings for OCR configuration."""
    settings.MIN_AVG_CHARS_FOR_TEXT_EXTRACTION = MIN_AVG_CHARS_FOR_TEXT_EXTRACTION
    settings.MIN_TEXT_COVERAGE_FOR_TEXT_EXTRACTION = 0.7
    settings.OCR_HRID = "test-ocr-hrid"
    settings.OCR_MODEL = "test-ocr-model"
    settings.OCR_TIMEOUT = 60
    settings.OCR_MAX_RETRIES = OCR_MAX_RETRIES
    settings.OCR_RETRY_DELAY = OCR_RETRY_DELAY
    settings.OCR_BATCH_PAGES = 10
    settings.LLM_CONFIGURATIONS = {
        "test-ocr-hrid": MagicMock(
            provider=MagicMock(
                base_url="https://ocr.example.com",
                api_key="test-api-key",
            )
        )
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
    parser = AdaptivePdfParser()
    reader = PdfReader(BytesIO(text_pdf_10_pages))

    result = parser.extract_page_batch(reader, 0, 1)

    result_reader = PdfReader(BytesIO(result))
    assert len(result_reader.pages) == 1


def test_extract_page_batch_multiple_pages(text_pdf_10_pages):
    """Should extract multiple pages correctly."""
    parser = AdaptivePdfParser()
    reader = PdfReader(BytesIO(text_pdf_10_pages))

    result = parser.extract_page_batch(reader, 2, 7)

    result_reader = PdfReader(BytesIO(result))
    assert len(result_reader.pages) == 5


def test_extract_page_batch_last_batch(text_pdf_10_pages):
    """Should handle last batch with fewer pages."""
    parser = AdaptivePdfParser()
    reader = PdfReader(BytesIO(text_pdf_10_pages))

    result = parser.extract_page_batch(reader, 7, 10)

    result_reader = PdfReader(BytesIO(result))
    assert len(result_reader.pages) == 3


def test_ocr_page_batch_success(text_pdf_1_page):
    """Should return markdown content on successful OCR."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "pages": [
                {"markdown": "# Page 1 content"},
            ]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

        assert result == ["# Page 1 content"]
        mock_post.assert_called_once()


def test_ocr_page_batch_retry_on_timeout(text_pdf_1_page):
    """Should retry on timeout with static delay."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.requests.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep") as mock_sleep:
            mock_post.side_effect = [
                requests.Timeout("Connection timed out"),
                MagicMock(
                    json=MagicMock(return_value={"pages": [{"markdown": "# Content"}]}),
                    raise_for_status=MagicMock(),
                ),
            ]

            result = parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

            assert result == ["# Content"]
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once_with(OCR_RETRY_DELAY)


def test_ocr_page_batch_fails_after_max_retries(text_pdf_1_page):
    """Should raise exception after max retries exceeded."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.requests.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            mock_post.side_effect = requests.Timeout("Connection timed out")

            with pytest.raises(requests.Timeout):
                parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

            assert mock_post.call_count == OCR_MAX_RETRIES


def test_ocr_page_batch_retry_on_request_exception(text_pdf_1_page):
    """Should retry on general request exceptions."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.requests.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            mock_post.side_effect = [
                requests.RequestException("Network error"),
                requests.RequestException("Network error"),
                MagicMock(
                    json=MagicMock(return_value={"pages": [{"markdown": "# Content"}]}),
                    raise_for_status=MagicMock(),
                ),
            ]

            result = parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

            assert result == ["# Content"]
            assert mock_post.call_count == 3


def test_parse_pdf_with_ocr_single_batch(text_pdf_10_pages):
    """Should process PDF in single batch when pages <= batch size."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.requests.post") as mock_post:
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

    with patch("chat.agent_rag.document_converter.parser.requests.post") as mock_post:
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


def test_parse_pdf_with_ocr_partial_failure(text_pdf_10_pages, settings):
    """Should insert empty placeholders for failed batches."""
    settings.OCR_BATCH_PAGES = 4  # Force multiple batches
    parser = AdaptivePdfParser()

    success_response = MagicMock()
    success_response.json.return_value = {"pages": [{"markdown": f"Page {i}"} for i in range(1, 5)]}
    success_response.raise_for_status = MagicMock()

    with patch("chat.agent_rag.document_converter.parser.requests.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            # First batch succeeds, then all retries fail for remaining batches
            mock_post.side_effect = [
                success_response,
                requests.Timeout("OCR failed"),
                requests.Timeout("OCR failed"),
                requests.Timeout("OCR failed"),
                requests.Timeout("OCR failed"),
                requests.Timeout("OCR failed"),
                requests.Timeout("OCR failed"),
            ]

            result = parser.parse_pdf_document_with_ocr("test.pdf", text_pdf_10_pages)

            parts = result.split("\n\n")
            # First batch succeeded (4 pages), remaining batches failed (6 pages as placeholders)
            assert len(parts) == 10
            assert parts[0] == "Page 1"
            assert parts[3] == "Page 4"
            assert parts[4] == ""  # Failed batch placeholder


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


def test_parse_document_non_pdf_uses_document_converter():
    """Should route non-PDF content to DocumentConverter."""
    parser = AdaptivePdfParser()

    with patch("chat.agent_rag.document_converter.parser.DocumentConverter") as mock_converter:
        mock_converter.return_value.convert_raw.return_value = "docx content"

        result = parser.parse_document("test.docx", "application/vnd.openxmlformats", b"content")

        assert result == "docx content"
        mock_converter.return_value.convert_raw.assert_called_once()
