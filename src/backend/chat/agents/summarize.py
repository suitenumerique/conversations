"""Build the summarization agent."""

import dataclasses
import logging
import asyncio

from django.conf import settings
from django.core.files.storage import default_storage

from asgiref.sync import sync_to_async
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from .base import BaseAgent
from ..tools.document_search_rag import add_document_rag_search_tool

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


async def hand_off_to_summarization_agent(
    ctx: RunContext, *, instructions: str | None = None
) -> ToolReturn:
    """
    Summarize the documents for the user, only when asked for.
    Instructions are optional but should reflect the user's request.
    Examples :
    "Résume ce doc en 2 paragraphes" -> instructions = "résumé en 2 paragraphes"
    "Résume ce doc en anglais" -> instructions = "In English"
    "Résume ce doc" -> instructions = "" (default)
    Args:
        instructions (str | None): The instructions the user gave to use for the summarization
    """
    summarization_agent = SummarizationAgent()

    prompt = (
        "Do not mention the user request in your answer.\n"
        "User request:\n"
        "{user_prompt}\n\n"
        "Document contents:\n"
        "{documents_prompt}\n"
    )

    # Collect documents content
    text_attachment = await sync_to_async(list)(
        ctx.deps.conversation.attachments.filter(
            content_type__startswith="text/",
        )
    )

    documents = [await read_document_content(doc) for doc in text_attachment]

    # Instructions: rely on tool argument only; model should extract them upstream
    if instructions is not None:
        instructions_hint: str = instructions.strip()
    else:
        instructions_hint = ""

    # Helpers
    def chunk_text(text: str, size: int = 10000) -> list[str]:
        if size <= 0:
            return [text]
        return [text[i : i + size] for i in range(0, len(text), size)]

    # 2) Chunk documents and summarize each chunk
    full_text = "\n\n".join(doc[1] for doc in documents)
    chunks = chunk_text(full_text, size=10000)
    logger.info(
        "[summarize] chunking: %s parts (size~%s), instructions='%s'",
        len(chunks),
        10000,
        instructions_hint or "",
    )

    async def summarize_chunk(idx, chunk, total_chunks, summarization_agent, ctx):
        sum_prompt = (
            "Tu es un agent spécialisé en synthèses de textes. "
            "Génère un résumé clair et concis du passage suivant (partie {idx}/{total}) :\n"
            "'''\n{context}\n'''\n\n"
        ).format(context=chunk, idx=idx, total=total_chunks)
        logger.info("[summarize] CHUNK %s/%s prompt=> %s", idx, total_chunks, sum_prompt[0:100]+'...')
        resp = await summarization_agent.run(sum_prompt, usage=ctx.usage)
        logger.info("[summarize] CHUNK %s/%s response<= %s", idx, total_chunks, resp.output or "")
        return resp.output or ""

    # Parallelize the chunk summarization in batches of 5 using asyncio.gather
    chunk_summaries: list[str] = []
    batch_size = 5
    for start_idx in range(0, len(chunks), batch_size):
        end_idx = start_idx + batch_size
        batch_chunks = chunks[start_idx:end_idx]
        summarization_tasks = [
            summarize_chunk(idx, chunk, len(chunks), summarization_agent, ctx)
            for idx, chunk in enumerate(batch_chunks, start=start_idx + 1)
        ]
        batch_results = await asyncio.gather(*summarization_tasks)
        chunk_summaries.extend(batch_results)

    if not instructions_hint:
        instructions_hint = "Le résumé doit être en Français, contenir 2 ou 3 parties."

    # 3) Merge chunk summaries into a single concise summary
    merged_prompt = (
        "Produit une synthèse cohérente à partir des résumés ci-dessous.\n\n"
        "'''\n{context}\n'''\n\n"
        "Contraintes :\n"
        "- Résumer sans répéter.\n"
        "- Harmoniser le style et la terminologie.\n"
        "- Le résumé final doit être bien structuré et formaté en markdown. \n"
        "- Respecter les consignes : {instructions}\n"
        "Réponds directement avec le résumé final."
    ).format(context="\n\n".join(chunk_summaries), instructions=instructions_hint or "")
    logger.info("[summarize] MERGE prompt=> %s", merged_prompt)
    merged_resp = await summarization_agent.run(merged_prompt, usage=ctx.usage)
    final_summary = (merged_resp.output or "").strip()
    logger.info("[summarize] MERGE response<= %s", final_summary)

    return ToolReturn(
        return_value=final_summary,
        metadata={"sources": {doc[0] for doc in documents}},
    )
