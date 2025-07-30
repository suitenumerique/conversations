"""Constants for RAG (Retrieval-Augmented Generation) results."""

from typing import List

from pydantic import BaseModel, Field


class RAGWebUsage(BaseModel):
    """
    Model representing the usage statistics for web results in RAG (Retrieval-Augmented Generation).
    """

    prompt_tokens: int = Field(default=0, description="Number of prompt tokens used.")
    completion_tokens: int = Field(default=0, description="Number of completion tokens generated.")


class RAGWebResult(BaseModel):
    """Model representing a single web result in RAG (Retrieval-Augmented Generation)."""

    url: str = Field(..., description="URL of the web result.")
    content: str = Field(..., description="Content of the web result chunk.")
    score: float = Field(
        ..., description="Relevance score of the web result, typically between 0 and 1."
    )


class RAGWebResults(BaseModel):
    """Model representing a list of web results in RAG (Retrieval-Augmented Generation)."""

    data: List[RAGWebResult]
    usage: RAGWebUsage = Field(..., description="RAG usage statistics.")

    def to_prompt(self) -> str:
        """Convert the web results to a prompt string."""
        _format = " - URL: {url}:\n   content: {content}\n\n"
        return (
            "\n\n".join(
                _format.format(url=result.url, content=result.content) for result in self.data
            )
            + "\n\n"
        )
