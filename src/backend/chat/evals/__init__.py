"""Shared Pydantic models for eval inputs and metadata."""

from typing import Literal

from pydantic import BaseModel


class EvalInputs(BaseModel):
    """Inputs for eval cases."""

    user_message: str
    tool_output: str | None = None
    requires_documents: bool = False
    # Fixture document names attached to the first turn (HTTP-target datasets).
    attachments: list[str] = []
    # Later user turns, sent in order in the same conversation; only the last
    # turn's answer is scored.
    follow_ups: list[str] = []
    # Project the conversation is created in (HTTP-target datasets): custom
    # instructions and fixture document names uploaded to the project.
    project_instructions: str | None = None
    project_attachments: list[str] = []
    # Long-chat validity: whether the target must (True) or must not (False)
    # summarize the conversation history; None skips the check.
    expect_history_summary: bool | None = None


class EvalMetadata(BaseModel):
    """Metadata for eval cases."""

    difficulty: Literal["easy", "medium", "hard"]
    category: str | None = None
    description: str | None = None
    doc_set: Literal["short", "long"] | None = None
