"""Tests for the document-parser resource-exhaustion guards."""

import io
import zipfile

import pytest
from pypdf import PdfWriter

from chat.agent_rag.document_converter.guards import (
    DocumentTooLargeError,
    guard_pdf_page_count,
    guard_zip_bomb,
)
from chat.agent_rag.document_converter.parser import analyze_pdf


def _make_zip(entries: dict[str, bytes]) -> bytes:
    """Build a ZIP archive (DEFLATE) from {name: content}."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _make_pdf(page_count: int) -> bytes:
    """Build a minimal PDF with the requested number of blank pages."""
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def parse_limits(settings):
    """Tight limits so tests don't need multi-MB fixtures."""
    settings.ATTACHMENT_PARSE_MAX_UNCOMPRESSED_SIZE = 1 * (2**20)  # 1MB
    settings.ATTACHMENT_PARSE_MAX_COMPRESSION_RATIO = 50
    settings.ATTACHMENT_PARSE_MAX_PDF_PAGES = 5
    return settings


def test_non_zip_content_is_ignored():
    """Plain bytes are not an archive and must pass through untouched."""
    guard_zip_bomb(b"just some plain text, not a zip")


def test_benign_zip_passes():
    """A small, normally-compressible archive is accepted."""
    guard_zip_bomb(_make_zip({"doc.xml": b"<root>hello world</root>" * 10}))


def test_rejects_oversized_uncompressed_total():
    """An archive whose declared uncompressed size exceeds the cap is rejected."""
    # 2MB of zeros compresses tiny but declares 2MB uncompressed (> 1MB cap).
    payload = _make_zip({"big.xml": b"\x00" * (2 * 2**20)})
    with pytest.raises(DocumentTooLargeError):
        guard_zip_bomb(payload)


def test_rejects_suspicious_compression_ratio():
    """An archive under the size cap but with an extreme ratio is rejected."""
    # 512KB of zeros: under the 1MB size cap, but ratio far exceeds 50x.
    payload = _make_zip({"bomb.xml": b"\x00" * (512 * 1024)})
    with pytest.raises(DocumentTooLargeError):
        guard_zip_bomb(payload)


def test_pdf_page_count_under_cap_passes():
    """A page count at or under the cap is accepted."""
    guard_pdf_page_count(5)


def test_pdf_page_count_over_cap_rejected():
    """A page count above the cap is rejected."""
    with pytest.raises(DocumentTooLargeError):
        guard_pdf_page_count(6)


def test_analyze_pdf_rejects_too_many_pages():
    """analyze_pdf enforces the page cap before the per-page extract loop."""
    with pytest.raises(DocumentTooLargeError):
        analyze_pdf(_make_pdf(6))


def test_analyze_pdf_accepts_pdf_within_cap():
    """A PDF within the page cap is analyzed normally."""
    result = analyze_pdf(_make_pdf(3))
    assert result["total_pages"] == 3
