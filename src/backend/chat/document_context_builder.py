"""Document-context instruction builder with FIFO inlining policy."""

import asyncio
import json
import logging
import sys
from collections import deque
from typing import Awaitable, Callable, Sequence

from chat import models


def _display_title_from_name(file_name: str | None, is_converted: bool) -> str:
    """Return user-facing title, preserving real markdown filenames."""
    title = file_name or ""
    return title.removesuffix(".md") if is_converted else title


def _build_payload(
    docs: list[dict],
    tool_call_only: bool,
) -> dict:
    """Build a payload with ordering and note."""
    note = (
        "Documents marked 'tool_call_only' are accessible through tools like "
        "RAG search or summary. "
    )
    if not tool_call_only:
        note += (
            "Documents marked 'full-context' can be directly "
            "manipulated by you, either for referencing, analysis or summarization. "
            "Do not use a tool to access a document marked 'full-context', this is "
            "counterproductive as the content is already available here."
        )
    payload = {
        "documents_order": "newest_to_oldest",
        "documents": [
            {
                "document_id": doc["document_id"],
                "title": doc["title"],
                "access": "tool_call_only" if tool_call_only else doc["access"],
                "content": None if tool_call_only else doc.get("content"),
                "info": doc.get("info"),
            }
            for doc in reversed(docs)
        ],
        "note": note,
    }

    return payload


async def build_document_context_instruction(  # noqa: PLR0913 # pylint: disable=too-many-arguments,too-many-locals
    *,
    text_attachments: Sequence[models.ChatConversationAttachment],
    model_hrid: str,
    model_max_context: int | None,
    budget_ratio: float,
    security_buffer_tokens: int,
    read_attachment_content: Callable[
        [models.ChatConversationAttachment], Awaitable[tuple[str, str]]
    ],
    count_approx_tokens: Callable[[str], int],
    logger: logging.Logger,
) -> str:
    """
    Build document instructions with a rolling full-context FIFO window.

    Rules:
    - Reserve a ratio of max model context for full document inclusion.
    - Keep all documents listed with an explicit accessibility status.
    - Apply FIFO eviction on inlined documents when budget is exceeded.
    """
    docs = [
        {
            "document_id": str(attachment.id),
            "title": _display_title_from_name(
                attachment.file_name, bool(getattr(attachment, "conversion_from", None))
            ),
        }
        for attachment in text_attachments
    ]
    if not text_attachments:
        return ""

    if not model_max_context:
        logger.warning(
            "Model '%s' has no max_token_context; skipping full document inlining.",
            model_hrid,
        )
        payload = _build_payload(docs=docs, tool_call_only=True)
        return (
            "List of documents attached to this conversation:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    if budget_ratio == 0:
        logger.info(
            "DOCUMENT_CONTEXT_BUDGET_RATIO is 0 for model '%s'; disabling full document inlining.",
            model_hrid,
        )
        payload = _build_payload(docs=docs, tool_call_only=True)
        return (
            "List of documents attached to this conversation:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    document_budget = max(int(model_max_context * budget_ratio) - security_buffer_tokens, 0)

    async def _load_document(index: int, attachment: models.ChatConversationAttachment) -> dict:
        try:
            title, content = await read_attachment_content(attachment)
            token_count = count_approx_tokens(content)
            access = "tool_call_only"
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "Could not inline attachment '%s'; keeping it tool_call_only: %s",
                getattr(attachment, "file_name", "<unknown>"),
                exc,
                exc_info=True,
            )
            title = getattr(attachment, "file_name", None)
            content = "available via tools"
            # Keep failed reads non-inlineable so they cannot be promoted later.
            access = "tool_call_only"
            token_count = sys.maxsize
        title = _display_title_from_name(title, bool(getattr(attachment, "conversion_from", None)))
        return {
            "document_id": str(getattr(attachment, "id", "")),
            "title": title,
            "content": content,
            "token_count": token_count,
            "access": access,
            "info": (
                "first_uploaded_document"
                if index == 1
                else "last_uploaded_document"
                if index == len(text_attachments)
                else None
            ),
        }

    docs = list(
        await asyncio.gather(
            *(
                _load_document(index, attachment)
                for index, attachment in enumerate(text_attachments, start=1)
            )
        )
    )

    inlined_docs = deque()  # More efficient than list for FIFO operations
    inlined_total = 0  # Total token count of inlined documents
    for doc in docs:
        token_count = doc["token_count"]
        if token_count > document_budget:
            # Document exceeds budget, keep it as tool_call_only
            doc["content"] = "available via tools"
            logger.debug(
                "Document '%s' (%s tokens) exceeds budget (%s); keeping tool_call_only.",
                doc["title"],
                token_count,
                document_budget,
            )
            continue

        # Evict documents until the new document fits within the budget
        while inlined_docs and inlined_total + token_count > document_budget:
            evicted = inlined_docs.popleft()  # Evict the oldest document
            inlined_total -= evicted["token_count"]  # update the total
            evicted["access"] = "tool_call_only"
            evicted["content"] = "available via tools"
            logger.debug("Evicted! Document title:%s", evicted["title"])

        # If the new document fits within the budget, add it to the inlined documents
        if inlined_total + token_count <= document_budget:
            logger.debug("Inlined! Document title:%s", doc["title"])
            doc["access"] = "full-context"
            inlined_docs.append(doc)
            inlined_total += token_count

    filled_ratio = (inlined_total / document_budget) if document_budget else 0
    logger.debug(
        (
            "Document context window usage - model=%s budget_ratio=%s "
            "document_budget_tokens=%s inlined_tokens=%s filled_ratio=%.4f "
            "total_documents=%s inlined_documents=%s"
        ),
        model_hrid,
        budget_ratio,
        document_budget,
        inlined_total,
        filled_ratio,
        len(docs),
        len(inlined_docs),
    )

    payload = _build_payload(docs=docs, tool_call_only=False)
    return (
        "List of documents attached to this conversation:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
