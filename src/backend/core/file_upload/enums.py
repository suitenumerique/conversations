"""File upload management enums declaration."""

import re
from enum import StrEnum

from django.conf import settings

ATTACHMENTS_FOLDER = "attachments"
UUID_REGEX = r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
FILE_EXT_REGEX = r"\.[a-zA-Z0-9]{1,10}"
MEDIA_STORAGE_URL_PATTERN = re.compile(
    f"{settings.MEDIA_URL:s}(?P<pk>{UUID_REGEX:s})/"
    f"(?P<attachment>{ATTACHMENTS_FOLDER:s}/{UUID_REGEX:s}(?:-unsafe)?{FILE_EXT_REGEX:s})$"
)
MEDIA_STORAGE_URL_EXTRACT = re.compile(
    f"{settings.MEDIA_URL:s}({UUID_REGEX}/{ATTACHMENTS_FOLDER}/{UUID_REGEX}{FILE_EXT_REGEX})"
)


class AttachmentStatus(StrEnum):
    """Defines the possible statuses for an attachment."""

    PENDING = "pending"
    UPLOADING = "uploading"
    ANALYZING = "analyzing"
    FILE_TOO_LARGE_TO_ANALYZE = "file_too_large_to_analyze"
    SUSPICIOUS = "suspicious"
    READY = "ready"

    @classmethod
    def choices(cls):
        """Return a list of tuples for each enum member."""
        return [(member.value, member.name) for member in cls]
