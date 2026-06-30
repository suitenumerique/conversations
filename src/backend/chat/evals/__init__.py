"""Shared Pydantic models for eval inputs and metadata."""

from typing import Literal

from pydantic import BaseModel


class EvalInputs(BaseModel):
    """Inputs for eval cases."""

    user_message: str
    tool_output: str | None = None
    requires_documents: bool = False


class EvalMetadata(BaseModel):
    """Metadata for eval cases."""

    difficulty: Literal["easy", "medium", "hard"]
    category: str | None = None
    description: str | None = None
