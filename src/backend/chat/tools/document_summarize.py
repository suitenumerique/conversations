"""Summarization tool used for uploaded documents."""

import asyncio
import logging

from django.conf import settings
from django.core.files.storage import default_storage

import semchunk
from asgiref.sync import sync_to_async
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from chat import models
from chat.agents.summarize import SummarizationAgent
from chat.constants import TEXT_MIME_PREFIX
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail, resolve_attachment_by_id

logger = logging.getLogger(__name__)


@sync_to_async
def read_document_content(doc):
    """Read document content asynchronously."""
    with default_storage.open(doc.key) as f:
        return doc.file_name, f.read().decode("utf-8")


async def _read_documents_safely(text_attachment, document_id):
    """
    Read each attachment from object storage individually so that one
    unreadable file (missing key, transient S3 error, decoding failure)
    does not abort the whole summarization. Behavior depends on whether
    the user targeted a specific document:
      - document_id set  -> the failure is fatal for THIS request: surface a
        doc-specific ModelCannotRetry instead of letting the outer except wrap
        it into a generic "unexpected error" message.
      - document_id None -> degrade gracefully: log the failure and skip the
        bad doc; keep summarizing the others.
    """
    documents = []
    for doc in text_attachment:
        try:
            documents.append(await read_document_content(doc))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to read attachment %s (%s): %s",
                doc.id,
                doc.file_name,
                exc,
                exc_info=True,
            )
            if document_id is not None:
                # Targeted summarization: there is no other document to fall
                # back to, so report this specific failure clearly.
                raise ModelCannotRetry(
                    f"Could not read the requested document '{doc.file_name}'. "
                    "You must explain this to the user and ask them to retry "
                    "or provide the document again."
                ) from exc
            # All-docs summarization: skip this one and keep going.
    return documents


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

    try:
        resp = await summarization_agent.run(sum_prompt, usage=ctx.usage)
    except Exception as exc:
        logger.warning("Error during chunk summarization: %s", exc, exc_info=True)
        raise ModelRetry(
            "An error occurred while summarizing a part of the document chunk."
        ) from exc

    logger.debug("[summarize] CHUNK %s/%s response<= %s", idx, total_chunks, resp.output or "")
    return resp.output or ""


async def merge_two_summaries(
    left: str,
    right: str,
    level: int,
    idx: int,
    total_pairs: int,
    summarization_agent: SummarizationAgent,
    ctx: RunContext,
    instructions_hint: str,
) -> str:
    """Merge two partial summaries into a single, more coherent one."""
    merge_prompt = (
        "You are an expert at hierarchical summarization.\n"
        "You receive two partial summaries that cover adjacent parts of the same document "
        "or set of documents. Merge them into a single, coherent summary that preserves all "
        "important information while eliminating redundancies.\n\n"
        f"Level: {level}, pair {idx}/{total_pairs}\n\n"
        "LEFT SUMMARY:\n"
        f"'''\n{left}\n'''\n\n"
        "RIGHT SUMMARY:\n"
        f"'''\n{right}\n'''\n\n"
        "Constraints:\n"
        "- Do not repeat information present in both summaries.\n"
        "- Harmonize style and terminology.\n"
        "- Keep a good level of detail; do not over-compress at this stage.\n"
        "- Structure the result clearly, using markdown when appropriate.\n"
        f"- Keep the user instructions for the final summary in mind: {instructions_hint}\n"
        "- This is not the final summary\n"
        "Respond directly with the merged summary."
    )

    logger.debug(
        "[summarize] TREE MERGE level=%s pair=%s/%s prompt=> %s",
        level,
        idx,
        total_pairs,
        merge_prompt[0:200] + "...",
    )

    try:
        resp = await summarization_agent.run(merge_prompt, usage=ctx.usage)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Error during hierarchical merge (level=%s, pair=%s/%s): %s",
            level,
            idx,
            total_pairs,
            exc,
            exc_info=True,
        )
        raise ModelRetry("An error occurred while merging partial summaries.") from exc

    output = (resp.output or "").strip()
    if not output:
        raise ModelRetry("The hierarchical merge produced an empty result.")

    logger.debug(
        "[summarize] TREE MERGE level=%s pair=%s/%s response<= %s",
        level,
        idx,
        total_pairs,
        output[0:200] + "...",
    )
    return output


async def merge_two_summaries_with_semaphore(
    left: str,
    right: str,
    level: int,
    idx: int,
    total_pairs: int,
    summarization_agent: SummarizationAgent,
    ctx: RunContext,
    instructions_hint: str,
    semaphore: asyncio.Semaphore,
) -> str:
    """Wrapper to run merge_two_summaries under a semaphore."""
    async with semaphore:
        return await merge_two_summaries(
            left,
            right,
            level,
            idx,
            total_pairs,
            summarization_agent,
            ctx,
            instructions_hint,
        )


async def hierarchical_merge_summaries(
    summaries: list[str],
    summarization_agent: SummarizationAgent,
    ctx: RunContext,
    instructions_hint: str,
    semaphore: asyncio.Semaphore | None = None,
    on_merge_done=None,
) -> str:
    """
    Merge a list of summaries using a binary tree strategy until a single root summary remains.
    """
    cleaned_summaries = [s.strip() for s in summaries if s and s.strip()]
    if not cleaned_summaries:
        raise ModelRetry("No summaries available to perform hierarchical merging.")
    if len(cleaned_summaries) == 1:
        return cleaned_summaries[0]

    level = 0
    current_level = cleaned_summaries

    while len(current_level) > 1:
        next_level: list[str] = []
        merge_tasks = []
        total_pairs = (len(current_level) + 1) // 2
        current_level_number = level
        current_total_pairs = total_pairs

        for i in range(0, len(current_level), 2):
            left = current_level[i]
            if i + 1 >= len(current_level):
                next_level.append(left)
                continue

            right = current_level[i + 1]
            pair_idx = (i // 2) + 1

            if semaphore is None:

                async def _merge_and_report(
                    left_summary: str, right_summary: str, pair_number: int
                ) -> str:
                    result = await merge_two_summaries(
                        left_summary,
                        right_summary,
                        current_level_number,
                        pair_number,
                        current_total_pairs,
                        summarization_agent,
                        ctx,
                        instructions_hint,
                    )
                    if on_merge_done:
                        on_merge_done()
                    return result

                merge_tasks.append(_merge_and_report(left, right, pair_idx))
            else:

                async def _merge_and_report(
                    left_summary: str, right_summary: str, pair_number: int
                ) -> str:
                    result = await merge_two_summaries_with_semaphore(
                        left_summary,
                        right_summary,
                        current_level_number,
                        pair_number,
                        current_total_pairs,
                        summarization_agent,
                        ctx,
                        instructions_hint,
                        semaphore,
                    )
                    if on_merge_done:
                        on_merge_done()
                    return result

                merge_tasks.append(_merge_and_report(left, right, pair_idx))

        if merge_tasks:
            merged_results = await asyncio.gather(*merge_tasks)
            next_level.extend(merged_results)

        current_level = next_level
        level += 1

    return current_level[0]


async def _summarize_text_attachments(  # pylint: disable=too-many-locals
    text_attachment: list,
    *,
    instructions: str | None,
    document_id: str | None,
    ctx: RunContext,
    empty_set_message: str,
) -> ToolReturn:
    """Run chunking + hierarchical merge summarization on the supplied attachments.

    Shared core for the conversation-scoped (`summarize`) and project-scoped
    (`summarize_project`) tools. The two tools differ only in which attachment
    set they fetch and the IDOR boundary they enforce - the rest of the
    pipeline (read, chunk, summarize, merge) is identical.

    `empty_set_message` is what the LLM sees when the resolved attachment list
    is empty before reading; this lets each caller produce scope-appropriate
    guidance ("no docs in this conversation" vs. "no project files").
    """
    instructions_hint = (
        instructions.strip() if instructions else "The summary should contain 2 or 3 parts."
    )
    summarization_agent = SummarizationAgent()

    if not text_attachment:
        raise ModelCannotRetry(empty_set_message)

    if document_id is not None:
        text_attachment = [resolve_attachment_by_id(text_attachment, document_id)]

    documents = await _read_documents_safely(text_attachment, document_id)

    # If every attachment failed to read we have nothing to summarize.
    # Stop here with a clear message rather than feeding an empty list to
    # the chunker & merge prompt downstream.
    if not documents:
        raise ModelCannotRetry(
            "None of the attached documents could be read. "
            "You must explain this to the user and ask them to retry "
            "or provide the documents again."
        )

    # Lightweight, optional progress reporting hook for the frontend.
    progress_callback = getattr(ctx.deps, "report_summarization_progress", None)

    def _report_progress(done: int, total: int, stage: str) -> None:
        if not progress_callback or total <= 0:
            return
        try:
            percent = int(done / total * 100) if total > 0 else 0
            message = f"{stage} {percent}%"
            progress_callback(message=message)
        except Exception:  # pylint: disable=broad-except
            # Progress reporting must never break summarization.
            logger.debug(
                "[summarize] progress callback failed (done=%s, total=%s, stage=%s)",
                done,
                total,
                stage,
            )

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

    # Estimate total work units for a simple progress percentage:
    # - one step per chunk summary
    # - one step per internal binary-tree merge per document (n_chunks - 1)
    # - one final merge step
    total_chunk_summaries = sum(len(chunks) for chunks in documents_chunks)
    total_hierarchical_merges = sum(max(0, len(doc_chunks) - 1) for doc_chunks in documents_chunks)
    total_steps = total_chunk_summaries + total_hierarchical_merges + 1
    completed_steps = 0
    _report_progress(completed_steps, total_steps, stage="Résumé en cours...")

    # Parallelize the chunk summarization with a semaphore to limit concurrent
    # tasks - it can be very resource intensive on the LLM backend.
    semaphore = asyncio.Semaphore(settings.SUMMARIZATION_CONCURRENT_REQUESTS)

    async def summarize_chunk_with_semaphore(idx, chunk, total_chunks):
        """Summarize a chunk with semaphore-controlled concurrency."""
        async with semaphore:
            result = await summarize_chunk(
                idx,
                chunk,
                total_chunks,
                summarization_agent,
                ctx,
            )
        nonlocal completed_steps
        completed_steps += 1
        _report_progress(completed_steps, total_steps, stage="Résumé en cours...")
        return result

    doc_chunk_summaries: list[list[str]] = []
    try:
        for doc_chunks in documents_chunks:
            summarization_tasks = [
                summarize_chunk_with_semaphore(idx, chunk, len(doc_chunks))
                for idx, chunk in enumerate(doc_chunks, start=1)
            ]
            chunk_summaries = await asyncio.gather(*summarization_tasks)
            doc_chunk_summaries.append(chunk_summaries)
    except ModelRetry as exc:
        logger.warning("Retryable error during chunk summarization: %s", exc, exc_info=True)
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Error during chunk summarization: %s", exc, exc_info=True)
        raise ModelRetry("An error occurred while processing document chunks.") from exc

    # First, build a root summary per document using hierarchical merging
    per_doc_root_summaries: list[tuple[str, str]] = []

    def _on_merge_done() -> None:
        nonlocal completed_steps
        completed_steps += 1
        _report_progress(completed_steps, total_steps, stage="Finalisation du résumé...")

    try:
        for (doc_name, _), chunk_summaries in zip(documents, doc_chunk_summaries, strict=True):
            root_summary = await hierarchical_merge_summaries(
                chunk_summaries,
                summarization_agent,
                ctx,
                instructions_hint,
                semaphore=semaphore,
                on_merge_done=_on_merge_done,
            )
            per_doc_root_summaries.append((doc_name, root_summary))
    except ModelRetry as exc:
        logger.warning("Retryable error during hierarchical document merge: %s", exc, exc_info=True)
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Error during hierarchical document merge: %s", exc, exc_info=True)
        raise ModelRetry("An error occurred while aggregating document summaries.") from exc

    # Build a concise context from per-document root summaries
    context = "\n\n".join(
        f"{doc_name}\n\n{doc_root_summary}" for doc_name, doc_root_summary in per_doc_root_summaries
    )

    # Merge per-document root summaries into a single concise summary
    merged_prompt = (
        "Produce a coherent synthesis from the high-level document summaries below.\n\n"
        f"'''\n{context}\n'''\n\n"
        "Constraints:\n"
        "- Summarize without repetition.\n"
        "- Harmonize style and terminology.\n"
        "- The final summary must be well-structured and formatted in markdown.\n"
        f"- Follow the instructions: {instructions_hint}\n"
        "Respond directly with the final summary."
    )

    logger.debug("[summarize] MERGE prompt=> %s", merged_prompt)

    try:
        merged_resp = await summarization_agent.run(merged_prompt, usage=ctx.usage)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Error during merge summarization: %s", exc, exc_info=True)
        raise ModelRetry("An error occurred while generating the final summary.") from exc

    final_summary = (merged_resp.output or "").strip()

    if not final_summary:
        raise ModelRetry("The summarization produced an empty result.")

    completed_steps += 1
    _report_progress(completed_steps, total_steps, stage="Résumé terminé.")

    logger.debug("[summarize] MERGE response<= %s", final_summary)

    return ToolReturn(
        return_value=final_summary,
        metadata={"sources": {doc[0] for doc in documents}},
    )


@last_model_retry_soft_fail
async def document_summarize(
    ctx: RunContext,
    *,
    instructions: str | None = None,
    document_id: str | None = None,
) -> ToolReturn:
    """
    Generate a complete, ready-to-use summary of the documents attached to the
    current conversation. Project-library files are summarized via the
    separate ``summarize_project`` tool.

    Instructions are optional but should reflect the user's request.

    Examples:
    "Summarize this doc in 2 paragraphs" -> instructions = "summary in 2 paragraphs"
    "Summarize this doc in English" -> instructions = "In English", document_id=None
    "Summarize this doc" -> instructions = "" (default), document_id=None
    "Summarize this specific doc" -> instructions = "", document_id=id_from_context

    Args:
        instructions (str | None): The instructions the user gave to use for the summarization
        document_id (str | None): Document UUID from the `documents` context array.
        If document_id is None, summarize every conversation document.
    """
    try:
        text_attachment_qs = ctx.deps.conversation.attachments.filter(
            content_type__startswith=TEXT_MIME_PREFIX
        ).order_by("created_at", "id")
        text_attachment = await sync_to_async(list)(text_attachment_qs)

        return await _summarize_text_attachments(
            text_attachment,
            instructions=instructions,
            document_id=document_id,
            ctx=ctx,
            empty_set_message=(
                "No text documents found in the conversation. "
                "You must explain this to the user and ask them to provide documents."
            ),
        )

    except (ModelCannotRetry, ModelRetry):
        # Re-raise these as-is
        raise
    except Exception as exc:
        # Unexpected error - stop and inform user
        logger.exception("Unexpected error in document_summarize: %s", exc)
        raise ModelCannotRetry(
            f"An unexpected error occurred during document summarization: {type(exc).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc


@last_model_retry_soft_fail
async def document_summarize_project(
    ctx: RunContext,
    *,
    instructions: str | None = None,
    document_id: str | None = None,
) -> ToolReturn:
    """
    Generate a complete, ready-to-use summary of project-library files
    (the documents listed under ``project_documents`` in the system context).

    Use this tool only when the user asks about project files. For files
    attached to the current conversation only, use ``summarize`` instead.

    Args:
        instructions (str | None): The instructions the user gave to use for the summarization
        document_id (str | None): Document UUID from the ``project_documents``
        context array. If None, summarize every project file.
    """
    try:
        project_id = getattr(ctx.deps.conversation, "project_id", None)
        if not project_id:
            raise ModelCannotRetry(
                "This conversation does not belong to a project, so there are no "
                "project files to summarize. You must explain this to the user."
            )

        text_attachment_qs = models.ChatConversationAttachment.objects.filter(
            project_id=project_id,
            content_type__startswith=TEXT_MIME_PREFIX,
        ).order_by("created_at", "id")
        text_attachment = await sync_to_async(list)(text_attachment_qs)

        return await _summarize_text_attachments(
            text_attachment,
            instructions=instructions,
            document_id=document_id,
            ctx=ctx,
            empty_set_message=(
                "No text documents found in the project library. "
                "You must explain this to the user and ask them to upload documents to the project."
            ),
        )

    except (ModelCannotRetry, ModelRetry):
        raise
    except Exception as exc:
        logger.exception("Unexpected error in document_summarize_project: %s", exc)
        raise ModelCannotRetry(
            "An unexpected error occurred during project document summarization: "
            f"{type(exc).__name__}. You must explain this to the user and not try "
            "to answer based on your knowledge."
        ) from exc
