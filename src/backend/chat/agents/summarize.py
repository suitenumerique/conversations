"""Build the summarization agent."""

import dataclasses
import logging

from django.conf import settings

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from ..models import ChatConversationContextKind
from .base import BaseAgent

logger = logging.getLogger(__name__)


@dataclasses.dataclass(init=False)
class SummarizationAgent(BaseAgent):
    """Create a Pydantic AI summarization Agent instance with the configured settings"""

    def __init__(self, **kwargs):
        """Initialize the agent with the configured model."""
        super().__init__(
            model_hrid=settings.LLM_SUMMARIZATION_MODEL_HRID,
            output_type=str,
            **kwargs,
        )


async def hand_off_to_summarization_agent(ctx: RunContext) -> ToolReturn:
    """
    Summarize the documents for the user, only when asked for,
    the documents are in my context.
    """
    summarization_agent = SummarizationAgent()

    prompt = (
        "Do not mention the user request in your answer.\n"
        "User request:\n"
        "{user_prompt}\n\n"
        "Document contents:\n"
        "{documents_prompt}\n"
    )
    documents = ctx.deps.conversation.contexts.filter(
        kind=ChatConversationContextKind.DOCUMENT.value,
    )
    documents_prompt = "\n\n".join(
        [
            (
                "<document>\n"
                f"<name>\n{doc.name}\n</name>\n"
                f"<content>\n{doc.content}\n</content>\n"
                "</document>"
            )
            async for doc in documents
        ]
    )

    formatted_prompt = prompt.format(
        user_prompt=ctx.prompt,
        documents_prompt=documents_prompt,
    )

    logger.debug("Summarize prompt: %s", formatted_prompt)

    response = await summarization_agent.run(formatted_prompt, usage=ctx.usage)

    logger.debug("Summarize response: %s", response)

    return ToolReturn(
        return_value=response.output,
        content=response.output,
        metadata={"sources": {doc.name async for doc in documents}},
    )
