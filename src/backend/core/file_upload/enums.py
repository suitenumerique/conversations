"""File upload management enums declaration."""

from enum import StrEnum

UUID_REGEX = r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
FILE_EXT_REGEX = r"\.[a-zA-Z0-9]{1,10}"


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
