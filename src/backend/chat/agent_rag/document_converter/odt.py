"""ODT Document Converter using odfdo"""

import zipfile
from io import BytesIO

from django.utils.translation import gettext_lazy as _

import structlog
from lxml.etree import XMLSyntaxError  # pylint: disable=no-name-in-module
from odfdo import Document

logger = structlog.get_logger(__name__)


class OdtParsingError(Exception):
    """Raised when an ODT file cannot be parsed."""


class OdtToMd:
    """Convert an ODT file to Markdown using odfdo."""

    def extract(self, content: bytes, **kwargs) -> str:
        """Extract markdown from odt"""
        try:
            doc = Document(BytesIO(content))
            return doc.to_markdown()
        except (TypeError, FileNotFoundError, zipfile.BadZipFile, XMLSyntaxError) as e:
            logger.error("odt_parse_failed", error_type=type(e).__name__)
            raise OdtParsingError(
                _("Failed to parse ODT document: %(error)s") % {"error": e}
            ) from e
