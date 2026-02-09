"""Document parsers for RAG backends."""

import base64
import logging
import time
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings
from pathlib import Path
import requests
from pypdf import PdfReader, PdfWriter
import subprocess
from chat.agent_rag.document_converter.markitdown import DocumentConverter
import tempfile

from .odt import OtdToMd

logger = logging.getLogger(__name__)


def odt_bytes_to_markdown(content: bytes) -> str:
    """Home implementation"""
    converter =  OtdToMd()
    return converter.extract(content)

def odt_bytes_to_markdown__(content: bytes) -> str:
    """Pandoc"""
    with tempfile.NamedTemporaryFile(suffix=".odt", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["pandoc", tmp_path, "-t", "markdown", "--wrap=none"],
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8")
    finally:
        Path(tmp_path).unlink()


class BaseParser:
    """Base class for document parsers."""

    def parse_document(self, name: str, content_type: str, content: bytes) -> str:
        """
        Parse the document and prepare it for the search operation.
        This method should handle the logic to convert the document
        into a format suitable for storage.

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (bytes): The content of the document as a bytes stream.

        Returns:
            str: The document content in Markdown format.
        """
        raise NotImplementedError("Must be implemented in subclass.")


class AlbertParser(BaseParser):
    """Document parser using Albert API for PDFs and DocumentConverter for other formats."""

    endpoint = urljoin(settings.ALBERT_API_URL, "/v1/parse-beta")

    def parse_pdf_document(self, name: str, content_type: str, content: bytes) -> str:
        """Parse PDF document using Albert API."""
        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
            },
            files={
                "file": (name, content, content_type),
                "output_format": (None, "markdown"),
            },
            timeout=settings.ALBERT_API_PARSE_TIMEOUT,
        )
        response.raise_for_status()

        return "\n\n".join(
            document_page["content"] for document_page in response.json().get("data", [])
        )

    def parse_document(self, name: str, content_type: str, content: bytes) -> str:
        """Parse document based on content type."""
        if content_type == "application/pdf":
            return self.parse_pdf_document(name=name, content_type=content_type, content=content)
        return DocumentConverter().convert_raw(
            name=name, content_type=content_type, content=content
        )


METHOD_TEXT_EXTRACTION = "text_extraction"
METHOD_OCR = "ocr"


def analyze_pdf(pdf_data: bytes) -> dict:
    """
    Analyze a PDF to determine if it needs OCR or can use direct text extraction.
    """
    reader = PdfReader(BytesIO(pdf_data))
    total_pages = len(reader.pages)
    if total_pages == 0:
        logger.info("No page found in pdf")
        return {
            "total_pages": 0,
            "pages_with_text": 0,
            "avg_chars_per_page": 0,
            "text_coverage": 0,
            "recommended_method": METHOD_TEXT_EXTRACTION,
        }

    total_chars = 0
    pages_with_text = 0
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        char_count = len(text)
        total_chars += char_count

        if char_count > 50:
            pages_with_text += 1

    avg_chars = total_chars / total_pages
    text_coverage = pages_with_text / total_pages

    # Decision logic
    if (
            avg_chars > settings.MIN_AVG_CHARS_FOR_TEXT_EXTRACTION
            and text_coverage > settings.MIN_TEXT_COVERAGE_FOR_TEXT_EXTRACTION
    ):
        method = METHOD_TEXT_EXTRACTION

    else:
        method = METHOD_OCR

    return {
        "total_pages": total_pages,
        "pages_with_text": pages_with_text,
        "avg_chars_per_page": round(avg_chars),
        "text_coverage": round(text_coverage, 2),
        "recommended_method": method,
    }


class AdaptiveParserMixin:
    """
    Mixin that adds adaptive PDF parsing behavior.

    Analyzes PDF content to choose between direct text extraction (fast) and OCR
    (for scanned/image PDFs). Subclasses must implement `parse_pdf_document_with_ocr`.
    """

    def parse_pdf_document(self, name: str, content_type: str, content: bytes) -> str:
        """Analyze PDF and route to text extraction or OCR based on content."""
        analysis = analyze_pdf(content)

        logger.info(
            "Pdf analysis - pages: %s, pages with text: %s, text_coverage: %s, "
            "recommended method: %s",
            analysis["total_pages"],
            analysis["pages_with_text"],
            analysis["text_coverage"],
            analysis["recommended_method"],
        )

        method = analysis["recommended_method"]
        if method == METHOD_TEXT_EXTRACTION:
            return self.extract_text_from_pdf(name=name, content_type=content_type, content=content)
        return self.parse_pdf_document_with_ocr(name=name, content=content)

    def extract_text_from_pdf(self, name: str, content_type: str, content: bytes) -> str:
        """Extract text directly from PDF without OCR (for text-based PDFs)."""
        logger.info("Parsing pdf with text extraction")
        return DocumentConverter().convert_raw(
            name=name, content_type=content_type, content=content
        )

    def parse_pdf_document_with_ocr(self, name: str, content: bytes) -> str:
        """Process PDF through OCR. Must be implemented by subclass."""
        raise NotImplementedError("Subclass must implement parse_pdf_document_with_ocr")


class AdaptivePdfParser(AdaptiveParserMixin, BaseParser):
    """
    PDF parser with adaptive text extraction / OCR routing.

    Uses Mistral OCR API for scanned/image PDFs, processed in batches with retry logic.
    """

    def __init__(self):
        super().__init__()

        self.endpoint = urljoin(
            settings.LLM_CONFIGURATIONS[settings.OCR_HRID].provider.base_url, "/v1/ocr"
        )
        self.max_retries = settings.OCR_MAX_RETRIES
        self.retry_delay = settings.OCR_RETRY_DELAY
        api_key = settings.LLM_CONFIGURATIONS[settings.OCR_HRID].provider.api_key

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def extract_page_batch(self, reader: PdfReader, start_index: int, end_index: int) -> bytes:
        """Extract a range of pages from PDF as a new PDF bytes object."""
        writer = PdfWriter()
        for i in range(start_index, end_index):
            writer.add_page(reader.pages[i])
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    def ocr_page_batch(
            self,
            name: str,
            page_content: bytes,
            start_index: int,
            end_index: int,
    ) -> list[str]:
        """Send page batch to Mistral OCR API with static delay retry."""
        file_data = base64.standard_b64encode(page_content).decode("utf-8")
        payload = {
            "document": {
                "type": "document_url",
                "document_name": f"{name}_pages_{start_index + 1}_to_{end_index}",
                "document_url": f"data:application/pdf;base64,{file_data}",
            },
            "model": settings.OCR_MODEL,
        }

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.endpoint,
                    headers=self.headers,
                    json=payload,
                    timeout=settings.OCR_TIMEOUT,
                )
                response.raise_for_status()

                pages = response.json().get("pages", [])
                return [page.get("markdown", "") for page in pages]

            except (requests.Timeout, requests.RequestException) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "OCR attempt %d/%d failed for pages %d-%d: %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        start_index + 1,
                        end_index,
                        str(e),
                        self.retry_delay,
                    )
                    time.sleep(self.retry_delay)

        logger.error(
            "OCR failed for pages %d-%d after %d attempts: %s",
            start_index + 1,
            end_index,
            self.max_retries,
            str(last_exception),
        )
        raise last_exception

    def parse_pdf_document_with_ocr(self, name: str, content: bytes) -> str:
        """Process PDF through OCR in batches, returning concatenated markdown."""
        reader = PdfReader(BytesIO(content))
        total_pages = len(reader.pages)
        batch_size = settings.OCR_BATCH_PAGES

        logger.info("Parsing pdf with OCR (%d pages, batch size %d)", total_pages, batch_size)

        results = []
        for start_index in range(0, total_pages, batch_size):
            end_index = min(start_index + batch_size, total_pages)
            batch_content = self.extract_page_batch(reader, start_index, end_index)
            try:
                batch_results = self.ocr_page_batch(name, batch_content, start_index, end_index)
                results.extend(batch_results)
                logger.debug(
                    "Completed OCR for pages %d-%d/%d", start_index + 1, end_index, total_pages
                )
            except Exception as e:  # pylint: disable=broad-except #noqa: BLE001
                logger.error("Failed to OCR pages %d-%d: %s", start_index + 1, end_index, str(e))
                # Preserve page count with empty placeholders to maintain correct ordering
                results.extend([""] * (end_index - start_index))

        return "\n\n".join(results)

    def parse_odt_document(self, name: str, content: bytes) -> str:

        output = odt_bytes_to_markdown(content)
        print("🚀️ ---------- parser.py l:298", output)
        return output

    def parse_document(self, name: str, content_type: str, content: bytes) -> str:
        """Route to PDF parser or DocumentConverter based on content type."""

        print("🚀️ ---------- parser.py l:282", content_type)
        if content_type == "application/pdf":
            return self.parse_pdf_document(name=name, content_type=content_type, content=content)
        if content_type == "application/vnd.oasis.opendocument.text":
            return self.parse_odt_document(name=name, content=content)

        return DocumentConverter().convert_raw(
            name=name, content_type=content_type, content=content
        )
