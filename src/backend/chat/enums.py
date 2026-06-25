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


class AttachmentIndexState(StrEnum):
    """Per-attachment RAG indexing lifecycle (project attachments).

    Distinct from the conversation-level `CollectionIndexState`: this tracks a
    single file's journey into the RAG backend, set by the project indexing
    task. `FAILED` is terminal until a manual re-index; `processing_error` on
    the attachment carries the reason.
    """

    NOT_INDEXED = "not_indexed"  # Default; not yet sent to the backend
    INDEXING = "indexing"  # Indexing task is running
    INDEXED = "indexed"  # Stored in the backend; rag_document_id is set
    FAILED = "failed"  # Last indexing attempt failed; see processing_error

    @classmethod
    def choices(cls):
        """Return a list of tuples for each enum member."""
        return [(member.value, member.name) for member in cls]
