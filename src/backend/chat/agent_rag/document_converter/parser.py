"""Document parsers for RAG backends."""

import base64
import logging
import time
from abc import ABC, abstractmethod
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings

import httpx
import pypdfium2
from pypdf import PdfReader, PdfWriter

from chat.agent_rag.document_converter.guards import guard_pdf_page_count, guard_zip_bomb
from chat.agent_rag.document_converter.markitdown import DocumentConverter
from chat.constants import PDF_MIME_TYPE
from chat.model_health import get_status_for_hrid
from chat.models import ModelHealth

from .odt import OdtToMd

logger = logging.getLogger(__name__)

CT_PDF = PDF_MIME_TYPE
CT_ODT = "application/vnd.oasis.opendocument.text"


class BaseParser(ABC):
    """Base class for document parsers.

    Routes documents by content type:
    - PDF -> self.parse_pdf_document() (must be provided by subclass or mixin)
    - ODT -> self.parse_odt_document() (must be provided by subclass or mixin)
    - Other -> DocumentConverter (markitdown)
    """

    def parse_document(self, name: str, content_type: str, content: bytes) -> str:
        """Route to the appropriate parser based on content type."""
        guard_zip_bomb(content)
        content_type = content_type.lower()
        if content_type == CT_PDF:
            return self.parse_pdf_document(name=name, content_type=content_type, content=content)
        if content_type == CT_ODT:
            return self.parse_odt_document(content=content)
        return DocumentConverter().convert_raw(
            name=name, content_type=content_type, content=content
        )

    @abstractmethod
    def parse_pdf_document(self, name: str, content_type: str, content: bytes) -> str:
        """Parse PDF document. Must be implemented by subclass or mixin."""

    @abstractmethod
    def parse_odt_document(self, content: bytes) -> str:
        """Parse ODT document. Must be implemented by subclass or mixin."""


class OdtParserMixin:
    """Mixin that adds ODT parsing using odfdo."""

    def parse_odt_document(self, content: bytes) -> str:
        """Parse ODT document using ofdo util."""
        return OdtToMd().extract(content)


class AlbertParser(OdtParserMixin, BaseParser):
    """Document parser using Albert API for PDFs.

    Sends every PDF to Albert's OCR endpoint, with no local analysis. Use
    AdaptivePdfParser instead to keep text-based PDFs out of OCR.
    """

    endpoint = urljoin(settings.ALBERT_API_URL, "/v1/ocr")

    def parse_pdf_document(self, name: str, content_type: str, content: bytes) -> str:
        """Parse PDF document using Albert API."""
        file_data = base64.standard_b64encode(content).decode("utf-8")
        response = httpx.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
            },
            json={
                "document": {
                    "type": "document_url",
                    "document_name": name,
                    "document_url": f"data:{content_type};base64,{file_data}",
                },
                "model": settings.OCR_MODEL,
            },
            timeout=settings.ALBERT_API_PARSE_TIMEOUT,
        )
        response.raise_for_status()

        return "\n\n".join(page.get("markdown", "") for page in response.json().get("pages", []))


METHOD_TEXT_EXTRACTION = "text_extraction"
METHOD_OCR = "ocr"


def analyze_pdf(pdf_data: bytes) -> dict:
    """Analyze a PDF to determine if it needs OCR or can use direct text extraction."""
    reader = PdfReader(BytesIO(pdf_data))
    total_pages = len(reader.pages)
    guard_pdf_page_count(total_pages)
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


class AdaptivePdfParserMixin:
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


class BaseOcrClient(ABC):
    """Shared plumbing for the OCR backends.

    Both take their provider, credentials and model from an LLM configuration
    entry, and both POST a JSON payload to a single endpoint with a static
    delay retry. What differs is the endpoint, the payload and how the answer
    is turned back into markdown.
    """

    endpoint_path: str

    def __init__(self, hrid: str):
        configuration = settings.LLM_CONFIGURATIONS[hrid]

        self.endpoint = urljoin(configuration.provider.base_url, self.endpoint_path)
        self.model_name = configuration.model_name
        self.headers = {
            "Authorization": f"Bearer {configuration.provider.api_key}",
            "Content-Type": "application/json",
        }
        self.max_retries = settings.OCR_MAX_RETRIES
        self.retry_delay = settings.OCR_RETRY_DELAY

    @property
    @abstractmethod
    def timeout(self) -> int:
        """Request timeout in seconds: a batch of pages, or a single one."""

    @abstractmethod
    def parse_pdf_document(self, name: str, content: bytes) -> str:
        """Return the document as markdown."""

    def post_with_retry(self, payload: dict, subject: str) -> dict:
        """POST `payload` and return the JSON body, retrying on HTTP errors.

        `subject` names what is being OCR'd in the logs (e.g. "pages 1-10").
        A request that fails every attempt raises, aborting the whole document.
        Substituting blank pages would return a partial parse the caller cannot
        tell from a complete one: it would be stored and indexed as a success,
        with the failed pages silently missing from the collection. Letting the
        error propagate sends the attachment to the caller's FAILED handling,
        which records the reason and leaves it re-indexable.
        """
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = httpx.post(
                    self.endpoint,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "OCR attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                        attempt + 1,
                        self.max_retries,
                        subject,
                        str(e),
                        self.retry_delay,
                    )
                    time.sleep(self.retry_delay)

        logger.error(
            "OCR failed for %s after %d attempts: %s",
            subject,
            self.max_retries,
            str(last_exception),
        )
        raise last_exception


class MistralOcr(BaseOcrClient):
    """Whole-document OCR through the provider's /v1/ocr endpoint, in page batches."""

    endpoint_path = "/v1/ocr"

    def __init__(self):
        super().__init__(settings.OCR_HRID)

    @property
    def timeout(self) -> int:
        """Covers a whole batch of pages."""
        return settings.OCR_TIMEOUT

    @staticmethod
    def extract_page_batch(reader: PdfReader, start_index: int, end_index: int) -> bytes:
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
        """Send a page batch to the OCR endpoint and return one markdown per page."""
        file_data = base64.standard_b64encode(page_content).decode("utf-8")
        payload = {
            "document": {
                "type": "document_url",
                "document_name": f"{name}_pages_{start_index + 1}_to_{end_index}",
                "document_url": f"data:application/pdf;base64,{file_data}",
            },
            "model": self.model_name,
        }

        body = self.post_with_retry(payload, f"pages {start_index + 1}-{end_index}")
        return [page.get("markdown", "") for page in body.get("pages", [])]

    def parse_pdf_document(self, name: str, content: bytes) -> str:
        """Process PDF through OCR in batches, returning concatenated markdown."""
        reader = PdfReader(BytesIO(content))
        total_pages = len(reader.pages)
        batch_size = settings.OCR_BATCH_PAGES

        logger.info("Parsing pdf with OCR (%d pages, batch size %d)", total_pages, batch_size)

        results = []
        for start_index in range(0, total_pages, batch_size):
            end_index = min(start_index + batch_size, total_pages)
            batch_content = self.extract_page_batch(reader, start_index, end_index)
            results.extend(self.ocr_page_batch(name, batch_content, start_index, end_index))
            logger.debug(
                "Completed OCR for pages %d-%d/%d", start_index + 1, end_index, total_pages
            )
        return "\n\n".join(results)


class LightOnOcr(BaseOcrClient):
    """Page-by-page OCR through a vision chat model (LightOn OCR).

    The OCR endpoint swallows a whole PDF and answers with one markdown blob
    per page. LightOn OCR is a vision-language model served on
    /v1/chat/completions instead: it only reads images, so each PDF page is
    rasterised to a PNG and sent as its own request.
    """

    endpoint_path = "/v1/chat/completions"

    def __init__(self):
        super().__init__(settings.OCR_FALLBACK_HRID)

    @property
    def timeout(self) -> int:
        """Covers a single page."""
        return settings.OCR_FALLBACK_TIMEOUT

    @staticmethod
    def render_page_to_png(page: pypdfium2.PdfPage) -> bytes:
        """Rasterise one PDF page to PNG bytes.

        The page is scaled so its longest side lands on
        ``OCR_FALLBACK_IMAGE_MAX_SIZE`` pixels, which is the resolution the
        model was trained on: rendering larger only inflates the payload.
        """
        longest_side = max(page.get_width(), page.get_height())
        scale = settings.OCR_FALLBACK_IMAGE_MAX_SIZE / longest_side

        buffer = BytesIO()
        page.render(scale=scale).to_pil().save(buffer, format="PNG")
        return buffer.getvalue()

    def ocr_page(self, page_png: bytes, page_number: int, total_pages: int) -> str:
        """Send one page image to the chat endpoint and return its markdown."""
        image_data = base64.standard_b64encode(page_png).decode("utf-8")
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_data}"},
                        }
                    ],
                }
            ],
            "max_tokens": settings.OCR_FALLBACK_MAX_TOKENS,
            "temperature": settings.OCR_FALLBACK_TEMPERATURE,
            "top_p": settings.OCR_FALLBACK_TOP_P,
        }

        body = self.post_with_retry(payload, f"page {page_number}/{total_pages}")
        choices = body.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        if not content:
            logger.warning("Fallback OCR returned no content for page %d", page_number)
        return content

    def parse_pdf_document(self, name: str, content: bytes) -> str:
        """Render every page and OCR it, returning concatenated markdown."""
        document = pypdfium2.PdfDocument(content)
        try:
            total_pages = len(document)
            logger.info(
                "Parsing %s with fallback OCR (%d pages, one request per page)", name, total_pages
            )

            results = []
            for index in range(total_pages):
                page_number = index + 1
                page_png = self.render_page_to_png(document[index])
                results.append(self.ocr_page(page_png, page_number, total_pages))
                logger.debug("Completed fallback OCR for page %d/%d", page_number, total_pages)
        finally:
            document.close()

        return "\n\n".join(results)


def use_fallback_ocr() -> bool:
    """True when OCR must be routed to the LightOn fallback model.

    Mistral OCR keeps the traffic unless its own health is reported as anything
    other than green *and* the fallback is green. When neither is green the
    document still goes to Mistral OCR, and is allowed to fail there: a
    fallback that is itself degraded is not an improvement over the primary.
    """
    fallback_hrid = settings.OCR_FALLBACK_HRID
    if not fallback_hrid:
        return False

    if get_status_for_hrid(settings.OCR_HRID) == ModelHealth.Status.GREEN:
        return False

    return get_status_for_hrid(fallback_hrid) == ModelHealth.Status.GREEN


class AdaptivePdfParser(AdaptivePdfParserMixin, OdtParserMixin, BaseParser):
    """
    PDF parser with adaptive text extraction / OCR routing.

    Scanned/image PDFs go to the Mistral OCR API, unless model health sends
    them to the LightOn fallback (see `use_fallback_ocr`).
    """

    def parse_pdf_document_with_ocr(self, name: str, content: bytes) -> str:
        """Send the document to whichever OCR model health says is usable."""
        if use_fallback_ocr():
            logger.info(
                "OCR model is not green, routing to the fallback model %s",
                settings.OCR_FALLBACK_HRID,
            )
            return LightOnOcr().parse_pdf_document(name=name, content=content)
        return MistralOcr().parse_pdf_document(name=name, content=content)
