"""Build the summarization agent."""

import asyncio
import dataclasses
import logging

from django.conf import settings
from django.core.files.storage import default_storage

import semchunk
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


async def summarize_chunk(idx, chunk, total_chunks, summarization_agent, ctx):
    """Summarize a single chunk of text."""
    sum_prompt = (
        "You are an agent specializing in text summarization. "
        "Generate a clear and concise summary of the following passage "
        f"(part {idx}/{total_chunks}):\n'''\n{chunk}\n'''\n\n"
    )

    logger.debug(
        "[summarize] CHUNK %s/%s prompt=> %s", idx, total_chunks, sum_prompt[0:100] + "..."
    )

    resp = await summarization_agent.run(sum_prompt, usage=ctx.usage)

    logger.debug("[summarize] CHUNK %s/%s response<= %s", idx, total_chunks, resp.output or "")
    return resp.output or ""


async def hand_off_to_summarization_agent(  # pylint: disable=too-many-locals
    ctx: RunContext, *, instructions: str | None = None
) -> ToolReturn:
    """
    Generate a complete, ready-to-use summary of the documents in context
    (do not request the documents to the user).
    Return this summary directly to the user WITHOUT any modification,
    or additional summarization.
    The summary is already optimized and MUST be presented as-is in the final response
    or translated preserving the information.

    Instructions are optional but should reflect the user's request.

    Examples:
    "Summarize this doc in 2 paragraphs" -> instructions = "summary in 2 paragraphs"
    "Summarize this doc in English" -> instructions = "In English"
    "Summarize this doc" -> instructions = "" (default)

    Args:
        instructions (str | None): The instructions the user gave to use for the summarization
    """
    instructions_hint = (
        instructions.strip() if instructions else "The summary should contain 2 or 3 parts."
    )
    summarization_agent = SummarizationAgent()

    # Collect documents content
    text_attachment = await sync_to_async(list)(
        ctx.deps.conversation.attachments.filter(
            content_type__startswith="text/",
        )
    )

    documents = [await read_document_content(doc) for doc in text_attachment]

    # Chunk documents and summarize each chunk
    chunk_size = settings.SUMMARIZATION_CHUNK_SIZE
    chunker = semchunk.chunkerify(
        tokenizer_or_token_counter=lambda text: len(text.split()),
        chunk_size=chunk_size,
    )
    documents_chunks = chunker(
        [doc[1] for doc in documents],
        overlap=settings.SUMMARIZATION_OVERLAP_SIZE,
    )

    logger.info(
        "[summarize] chunking: %s parts (size~%s), instructions='%s'",
        sum(len(chunks) for chunks in documents_chunks),
        chunk_size,
        instructions_hint,
    )

    # Parallelize the chunk summarization with a semaphore to limit concurrent tasks
    # because it can be very resource intensive on the LLM backend
    semaphore = asyncio.Semaphore(settings.SUMMARIZATION_CONCURRENT_REQUESTS)

    async def summarize_chunk_with_semaphore(idx, chunk, total_chunks):
        """Summarize a chunk with semaphore-controlled concurrency."""
        async with semaphore:
            return await summarize_chunk(idx, chunk, total_chunks, summarization_agent, ctx)

    doc_chunk_summaries = []
    for doc_chunks in documents_chunks:
        summarization_tasks = [
            summarize_chunk_with_semaphore(idx, chunk, len(doc_chunks))
            for idx, chunk in enumerate(doc_chunks, start=1)
        ]
        chunk_summaries = await asyncio.gather(*summarization_tasks)
        doc_chunk_summaries.append(chunk_summaries)

    context = "\n\n".join(
        doc_name + "\n\n" + "\n\n".join(summaries)
        for doc_name, summaries in zip(
            (doc[0] for doc in documents),
            doc_chunk_summaries,
            strict=True,
        )
    )

    # Merge chunk summaries into a single concise summary
    merged_prompt = (
        "Produce a coherent synthesis from the summaries below.\n\n"
        f"'''\n{context}\n'''\n\n"
        "Constraints:\n"
        "- Summarize without repetition.\n"
        "- Harmonize style and terminology.\n"
        "- The final summary must be well-structured and formatted in markdown.\n"
        f"- Follow the instructions: {instructions_hint}\n"
        "Respond directly with the final summary."
    )

    logger.debug("[summarize] MERGE prompt=> %s", merged_prompt)

    merged_resp = await summarization_agent.run(merged_prompt, usage=ctx.usage)

    final_summary = (merged_resp.output or "").strip()

    logger.debug("[summarize] MERGE response<= %s", final_summary)

    return ToolReturn(
        return_value=final_summary,
        metadata={"sources": {doc[0] for doc in documents}},
    )
