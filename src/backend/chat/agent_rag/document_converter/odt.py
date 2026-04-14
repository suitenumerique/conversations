"""ODT Document Converter using odfdo"""

import logging
import zipfile
from io import BytesIO

from django.utils.translation import gettext_lazy as _

from lxml.etree import XMLSyntaxError  # pylint: disable=no-name-in-module
from odfdo import Document

logger = logging.getLogger(__name__)


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
            logger.error("Failed to parse ODT document: %s", e)
            raise OdtParsingError(
                _("Failed to parse ODT document: %(error)s") % {"error": e}
            ) from e
