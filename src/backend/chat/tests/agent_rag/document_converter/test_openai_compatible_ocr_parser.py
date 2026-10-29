"""Tests for OpenAICompatibleOcrParser."""

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from chat.agent_rag.document_converter.parser import (
    OpenAICompatibleOcrParser,
    strip_enclosing_code_fences,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

OCR_RETRY_DELAY = 1
OCR_MAX_RETRIES = 3


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


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Mock Django settings for OpenAI-compatible OCR configuration."""
    settings.OCR_HRID = "test-ocr-hrid"
    settings.OCR_MODEL = "lightonocr-3-0.8b"
    settings.OCR_TIMEOUT = 60
    settings.OCR_MAX_RETRIES = OCR_MAX_RETRIES
    settings.OCR_RETRY_DELAY = OCR_RETRY_DELAY
    settings.OCR_PROMPT = None
    settings.LLM_CONFIGURATIONS = {
        "test-ocr-hrid": MagicMock(
            provider=MagicMock(
                base_url="https://api.scaleway.ai/test-project-id/v1/",
                api_key="test-api-key",
            )
        )
    }
    return settings


def _chat_completion_response(content):
    """Build a mocked successful chat completions response."""
    return MagicMock(
        json=MagicMock(return_value={"choices": [{"message": {"content": content}}]}),
        raise_for_status=MagicMock(),
    )


def test_ocr_endpoint_keeps_base_url_path():
    """The endpoint should extend the provider base URL, keeping its path (project ID)."""
    parser = OpenAICompatibleOcrParser()

    assert parser.endpoint == "https://api.scaleway.ai/test-project-id/v1/chat/completions"
    assert parser.headers["Authorization"] == "Bearer test-api-key"


def test_ocr_page_batch_success(text_pdf_1_page):
    """Should send the batch as a chat completions file and return its markdown."""
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value = _chat_completion_response("# Page 1 content")

        result = parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

    assert result == ["# Page 1 content"]
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == (
        "https://api.scaleway.ai/test-project-id/v1/chat/completions"
    )
    assert mock_post.call_args.kwargs["timeout"] == 60

    file_data = base64.standard_b64encode(text_pdf_1_page).decode("utf-8")
    assert mock_post.call_args.kwargs["json"] == {
        "model": "lightonocr-3-0.8b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {"file_data": f"data:application/pdf;base64,{file_data}"},
                    }
                ],
            }
        ],
        "stream": False,
    }


def test_ocr_page_batch_sends_prompt_when_set(text_pdf_1_page, settings):
    """OCR_PROMPT should be sent as a text part after the PDF, for vision LLMs."""
    settings.OCR_PROMPT = "Transcribe this document to markdown."
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value = _chat_completion_response("# Content")

        parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

    content = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert [part["type"] for part in content] == ["file", "text"]
    assert content[1]["text"] == "Transcribe this document to markdown."


@pytest.mark.parametrize(
    "response_data",
    [
        {"choices": []},
        {},
        {"choices": [{"message": {"content": None}}]},
    ],
)
def test_ocr_page_batch_empty_response(text_pdf_1_page, response_data):
    """Should return an empty markdown string when the response has no content."""
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value.json.return_value = response_data
        mock_post.return_value.raise_for_status = MagicMock()

        result = parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

    assert result == [""]


def test_ocr_page_batch_retry_on_http_error(text_pdf_1_page):
    """Should retry on HTTP errors with static delay."""
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep") as mock_sleep:
            mock_post.side_effect = [
                httpx.TimeoutException("Connection timed out"),
                _chat_completion_response("# Content"),
            ]

            result = parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

    assert result == ["# Content"]
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(OCR_RETRY_DELAY)


def test_ocr_page_batch_fails_after_max_retries(text_pdf_1_page):
    """Should raise the httpx exception after max retries exceeded."""
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        with patch("chat.agent_rag.document_converter.parser.time.sleep"):
            mock_post.side_effect = httpx.TimeoutException("Connection timed out")

            with pytest.raises(httpx.TimeoutException):
                parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

    assert mock_post.call_count == OCR_MAX_RETRIES


def test_parse_pdf_with_ocr_multiple_batches(text_pdf_10_pages, settings):
    """Should send one request per batch and join the batch markdowns."""
    settings.OCR_BATCH_PAGES = 4
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.side_effect = [
            _chat_completion_response("Pages 1-4"),
            _chat_completion_response("Pages 5-8"),
            _chat_completion_response("Pages 9-10"),
        ]

        result = parser.parse_pdf_document_with_ocr("test.pdf", text_pdf_10_pages)

    assert mock_post.call_count == 3
    assert result == "Pages 1-4\n\nPages 5-8\n\nPages 9-10"


def test_parse_document_routes_scanned_pdf_to_ocr(mixed_pdf_10_pages):
    """A low-text PDF should go through the chat completions OCR endpoint."""
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value = _chat_completion_response("# OCR content")

        result = parser.parse_document("scan.pdf", "application/pdf", mixed_pdf_10_pages)

    assert result == "# OCR content"
    mock_post.assert_called_once()


def test_parse_document_skips_ocr_for_text_pdf(text_pdf_10_pages):
    """A text-based PDF should be extracted locally, without calling the OCR endpoint."""
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        result = parser.parse_document("text.pdf", "application/pdf", text_pdf_10_pages)

    assert result
    mock_post.assert_not_called()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("```text\n# Title\n\nBody\n```", "# Title\n\nBody"),
        ("```\n# Title\n```\n", "# Title"),
        ("```markdown\n# Title\n\nUnclosed", "# Title\n\nUnclosed"),
        ("# Title\n\nBody", "# Title\n\nBody"),
        ("```python\nprint(1)\n```\n\nText after", "```python\nprint(1)\n```\n\nText after"),
        ("```\nPage 1\n```\n\n```\n# Page 2\n```", "Page 1\n\n# Page 2"),
        ("```\nPage 1\n```\n\n```\n# Page 2", "Page 1\n\n# Page 2"),
        ("```\n# Title\n```\nText outside", "```\n# Title\n```\nText outside"),
        ("", ""),
    ],
)
def test_strip_enclosing_code_fences(content, expected):
    """Only a fence wrapping the whole OCR output should be removed."""
    assert strip_enclosing_code_fences(content) == expected


def test_ocr_page_batch_strips_enclosing_code_fences(text_pdf_1_page):
    """The markdown returned by the model should not stay wrapped in a code block."""
    parser = OpenAICompatibleOcrParser()

    with patch("chat.agent_rag.document_converter.parser.httpx.post") as mock_post:
        mock_post.return_value = _chat_completion_response("```text\n# Page 1\n```")

        result = parser.ocr_page_batch("test.pdf", text_pdf_1_page, 0, 1)

    assert result == ["# Page 1"]
