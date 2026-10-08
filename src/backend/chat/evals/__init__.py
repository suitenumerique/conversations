"""Shared Pydantic models for eval inputs and metadata."""

from typing import Literal

from pydantic import BaseModel


class HistoryMessage(BaseModel):
    """A message of the conversation before the case's first turn."""

    role: Literal["user", "assistant"]
    content: str


class EvalInputs(BaseModel):
    """Inputs for eval cases."""

    user_message: str
    tool_output: str | None = None
    requires_documents: bool = False
    # Fixture document names attached to the conversation.
    attachments: list[str] = []
    # Later user turns, sent in order in the same conversation; only the last
    # turn's answer is scored.
    follow_ups: list[str] = []
    # Project the conversation belongs to: custom instructions and fixture
    # document names in the project's library.
    project_instructions: str | None = None
    project_attachments: list[str] = []
    # State of a long conversation after history summarization: the stored
    # summary, and the recent messages kept verbatim. `{{paste:<name>}}` in a
    # message's content is replaced with the fixture's text.
    history_summary: str | None = None
    message_history: list[HistoryMessage] = []


class EvalMetadata(BaseModel):
    """Metadata for eval cases."""

    difficulty: Literal["easy", "medium", "hard"]
    category: str | None = None
    description: str | None = None
    doc_set: Literal["short", "long"] | None = None
