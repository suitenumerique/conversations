"""Chat conversation collection index state enums declaration."""

from enum import StrEnum


class CollectionIndexState(StrEnum):
    """Defines the possible index states for a conversation's collection."""

    UNINDEXED = "unindexed"  # No collection; default for all new conversations
    DEINDEXED = "deindexed"  # Was indexed, then de-indexed by the inactivity command
    INDEXING = "indexing"  # Claim held, reindex in progress
    INDEXED = "indexed"  # Collection exists; collection_id holds real backend ID
    ERROR = "error"  # Last attempt failed; will retry on next request

    @classmethod
    def choices(cls):
        """Return a list of tuples for each enum member."""
        return [(member.value, member.name) for member in cls]
