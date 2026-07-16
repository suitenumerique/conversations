"""Resource-exhaustion guards for the document parsing pipeline.

These run before the format-specific parsers to bound the damage a single
malicious upload can do to the parsing process. Parsing runs in a Celery worker
under the task time limits, which bound wall-clock but not memory: a
decompression bomb can OOM the worker child well before any timeout fires.
These guards close that gap; a memory-capped (cgroup) worker remains the
complete fix for what they cannot see (see limitations on each guard).
"""

import logging
import zipfile
from io import BytesIO

from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class DocumentTooLargeError(Exception):
    """Raised when a document would expand beyond the configured parse limits."""


def guard_zip_bomb(content: bytes) -> None:
    """Reject ZIP-container documents that declare an unsafe expansion.

    DOCX/XLSX/PPTX/ODT are ZIP archives. The upload size cap bounds the
    *compressed* bytes, but a decompression bomb can expand to many GB and OOM
    the parser process. We read the *declared* uncompressed sizes from the ZIP
    central directory (cheap, no decompression) and reject if the total size or
    the overall compression ratio exceeds the configured ceilings.

    Non-ZIP content (txt, csv, html, md, pdf) is ignored: it is not an archive
    and cannot be a classic decompression bomb.

    Limitations (a crafted archive can evade this, hence "first line of
    defense", not a complete one):
    - The central-directory sizes can be under-reported; a hard cap *during*
      extraction (only achievable out-of-process) is the eventual fix.
    - Nested ZIPs (zip-in-zip) hide inner expansion behind one entry. Office
      parsers don't recurse into nested archives, so this matches their actual
      read behaviour, but it is not a general anti-bomb check.
    """
    if not zipfile.is_zipfile(BytesIO(content)):
        return

    with zipfile.ZipFile(BytesIO(content)) as archive:
        infos = archive.infolist()

    total_uncompressed = sum(info.file_size for info in infos)
    total_compressed = sum(info.compress_size for info in infos)

    max_uncompressed = settings.ATTACHMENT_PARSE_MAX_UNCOMPRESSED_SIZE
    if total_uncompressed > max_uncompressed:
        logger.warning(
            "Rejected document: declared uncompressed size %d bytes exceeds limit %d.",
            total_uncompressed,
            max_uncompressed,
        )
        raise DocumentTooLargeError(_("Document expands beyond the allowed size and was rejected."))

    max_ratio = settings.ATTACHMENT_PARSE_MAX_COMPRESSION_RATIO
    if total_compressed > 0:
        ratio = total_uncompressed / total_compressed
        if ratio > max_ratio:
            logger.warning(
                "Rejected document: compression ratio %.1f exceeds limit %d.",
                ratio,
                max_ratio,
            )
            raise DocumentTooLargeError(
                _("Document has a suspicious compression ratio and was rejected.")
            )


def guard_pdf_page_count(total_pages: int) -> None:
    """Reject PDFs whose page count exceeds the configured ceiling.

    Only relevant when PDFs are parsed *in process* (the AdaptivePdfParser path,
    which loops `extract_text()` over every page). PDFs are not ZIP archives, so
    `guard_zip_bomb` skips them; this caps the per-page work instead. A PDF
    declaring an enormous page count can pin CPU/memory in that loop long before
    the wall-clock timeout releases the chat turn.

    Limitation: this bounds the *number* of pages, not the size of any single
    page's compressed content stream. A few-page PDF with a multi-GB FlateDecode
    stream can still expand on extraction; only an out-of-process parser with a
    hard memory limit closes that gap (same eventual fix as `guard_zip_bomb`).
    """
    max_pages = settings.ATTACHMENT_PARSE_MAX_PDF_PAGES
    if total_pages > max_pages:
        logger.warning(
            "Rejected PDF: page count %d exceeds limit %d.",
            total_pages,
            max_pages,
        )
        raise DocumentTooLargeError(_("Document has too many pages and was rejected."))
