"""Shared Pydantic models for eval inputs and metadata."""

from typing import Literal

from pydantic import BaseModel


class EvalDocsLink(BaseModel):
    """A Docs link pasted in the user message, and what reading it returned."""

    # "read", or a chat.docs_client.DocsFetchFailure value.
    outcome: Literal[
        "read",
        "unauthenticated",
        "forbidden",
        "not_found",
        "unavailable",
        "too_large",
        "empty",
        "storage_failed",
    ]
    title: str = "Document"
    content: str | None = None
    access: Literal["full-context", "tool_call_only"] = "full-context"


class EvalInputs(BaseModel):
    """Inputs for eval cases."""

    user_message: str
    tool_output: str | None = None
    requires_documents: bool = False
    docs_links: list[EvalDocsLink] = []


class EvalMetadata(BaseModel):
    """Metadata for eval cases."""

    difficulty: Literal["easy", "medium", "hard"]
    category: str | None = None
    description: str | None = None
