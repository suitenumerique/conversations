"""Registry mapping short backend keys to their dotted import paths."""

from django.db import models


class RagBackend(models.TextChoices):
    ALBERT = "albert", "Albert"
    FIND = "find", "Find"


RAG_BACKEND_CLASSES = {
    RagBackend.ALBERT: "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend",
    RagBackend.FIND: "chat.agent_rag.document_rag_backends.find_rag_backend.FindRagBackend",
}

# Reverse lookup: dotted path -> short key
RAG_BACKEND_KEYS = {v: k for k, v in RAG_BACKEND_CLASSES.items()}


def get_backend_key(dotted_path: str) -> str:
    """Resolve a dotted import path (e.g. from settings) to the short RagBackend key."""
    return RAG_BACKEND_KEYS[dotted_path]
