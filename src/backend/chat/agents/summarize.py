"""Build the summarization agent."""

import dataclasses
import logging

from django.conf import settings
from django.core.files.storage import default_storage

from asgiref.sync import sync_to_async
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

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


@sync_to_async
def read_document_content(doc):
    """Read document content asynchronously."""
    with default_storage.open(doc.key) as f:
        return doc.file_name, f.read().decode("utf-8")


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
    text_attachment = await sync_to_async(list)(
        ctx.deps.conversation.attachments.filter(
            content_type__startswith="text/",
        )
    )

    documents = [await read_document_content(doc) for doc in text_attachment]

    documents_prompt = "\n\n".join(
        [
            (f"<document>\n<name>\n{name}\n</name>\n<content>\n{content}\n</content>\n</document>")
            for name, content in documents
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
        metadata={"sources": {doc[0] for doc in documents}},
    )
