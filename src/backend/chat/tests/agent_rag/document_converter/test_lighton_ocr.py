"""Tests for the LightOn OCR fallback (page-by-page vision chat model)."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pypdfium2
import pytest
from PIL import Image

from chat.agent_rag.document_converter.parser import LightOnOcr

FIXTURES_DIR = Path(__file__).parent / "fixtures"

OCR_RETRY_DELAY = 1
OCR_MAX_RETRIES = 3


@pytest.fixture(name="text_pdf_1_page")
def provide_text_pdf_1_page():
    """Load a 1 page PDF with extractable text."""
    return (FIXTURES_DIR / "text_pdf_1_page.pdf").read_bytes()


@pytest.fixture(name="text_pdf_10_pages")
def provide_text_pdf_10_pages():
    """Load a 10-page PDF with extractable text."""
    return (FIXTURES_DIR / "text_10_pages.pdf").read_bytes()


@pytest.fixture(autouse=True)
def fallback_ocr_settings(settings):
    """Mock Django settings for the fallback OCR configuration."""
    settings.OCR_FALLBACK_HRID = "test-ocr-fallback-hrid"
    settings.OCR_FALLBACK_IMAGE_MAX_SIZE = 1540
    settings.OCR_FALLBACK_MAX_TOKENS = 4096
    settings.OCR_FALLBACK_TEMPERATURE = 0.2
    settings.OCR_FALLBACK_TOP_P = 0.9
    settings.OCR_FALLBACK_TIMEOUT = 60
    settings.OCR_MAX_RETRIES = OCR_MAX_RETRIES
    settings.OCR_RETRY_DELAY = OCR_RETRY_DELAY
    settings.LLM_CONFIGURATIONS = {
        "test-ocr-fallback-hrid": MagicMock(
            model_name="test-ocr-fallback-model",
            provider=MagicMock(
                hrid="albert",
                base_url="https://ocr.example.com",
                api_key="test-fallback-api-key",
            ),
        )
    }
    return settings


def chat_response(content):
    """Build a mocked chat completions response carrying `content`."""
    return MagicMock(
        json=MagicMock(return_value={"choices": [{"message": {"content": content}}]}),
        raise_for_status=MagicMock(),
    )


def test_endpoint_and_headers_come_from_the_fallback_provider():
    """The fallback talks to the chat endpoint, not the OCR one."""
    ocr = LightOnOcr()

    assert ocr.endpoint == "https://ocr.example.com/v1/chat/completions"
    assert ocr.headers["Authorization"] == "Bearer test-fallback-api-key"


def test_render_page_to_png_scales_to_configured_size(text_pdf_1_page, settings):
    """Pages are rasterised to PNG with their longest side on the configured size."""
    settings.OCR_FALLBACK_IMAGE_MAX_SIZE = 400
    document = pypdfium2.PdfDocument(text_pdf_1_page)

    result = LightOnOcr().render_page_to_png(document[0])

    image = Image.open(BytesIO(result))
    assert image.format == "PNG"
    assert max(image.size) == pytest.approx(400, abs=1)


def test_ocr_page_sends_the_image_and_returns_markdown():
    """A page is posted as a base64 PNG data URL and its markdown returned."""
    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value = chat_response("# Page 1 content")

        result = LightOnOcr().ocr_page(b"fake-png-bytes", 1, 1)

        assert result == "# Page 1 content"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "test-ocr-fallback-model"
        image_url = payload["messages"][0]["content"][0]["image_url"]["url"]
        assert image_url.startswith("data:image/png;base64,")


def test_ocr_page_retries_then_succeeds():
    """Should retry on HTTP errors with a static delay."""
    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep") as mock_sleep:
            mock_post.side_effect = [
                httpx.TimeoutException("Connection timed out"),
                chat_response("# Content"),
            ]

            result = LightOnOcr().ocr_page(b"fake-png-bytes", 1, 1)

            assert result == "# Content"
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once_with(OCR_RETRY_DELAY)


def test_ocr_page_fails_after_max_retries():
    """Should raise once the retries are exhausted."""
    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            mock_post.side_effect = httpx.TimeoutException("Connection timed out")

            with pytest.raises(httpx.TimeoutException):
                LightOnOcr().ocr_page(b"fake-png-bytes", 1, 1)

            assert mock_post.call_count == OCR_MAX_RETRIES


def test_ocr_page_tolerates_an_empty_answer():
    """A page the model returns nothing for yields an empty string, not a crash."""
    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            json=MagicMock(return_value={"choices": []}),
            raise_for_status=MagicMock(),
        )

        assert LightOnOcr().ocr_page(b"fake-png-bytes", 1, 1) == ""


def test_parse_pdf_document_sends_one_request_per_page(text_pdf_10_pages):
    """Every page gets its own request and the markdown is concatenated."""
    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.side_effect = [chat_response(f"Page {i}") for i in range(1, 11)]

        result = LightOnOcr().parse_pdf_document("test.pdf", text_pdf_10_pages)

        assert mock_post.call_count == 10
        assert result == "\n\n".join(f"Page {i}" for i in range(1, 11))


def test_parse_pdf_document_page_failure_aborts_document(text_pdf_10_pages):
    """A page that exhausts its retries fails the whole document."""
    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            mock_post.side_effect = [
                chat_response("Page 1"),
                httpx.TimeoutException("OCR failed"),
                httpx.TimeoutException("OCR failed"),
                httpx.TimeoutException("OCR failed"),
            ]

            with pytest.raises(httpx.TimeoutException):
                LightOnOcr().parse_pdf_document("test.pdf", text_pdf_10_pages)

            # Aborted on the failed page: the remaining pages are never sent.
            assert mock_post.call_count == 4
