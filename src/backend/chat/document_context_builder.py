"""Document-context instruction builder with FIFO inlining policy."""

import asyncio
import dataclasses
import functools
import json
import logging
from collections import deque
from typing import Literal, Sequence

from django.core.files.storage import default_storage

import tiktoken
from asgiref.sync import sync_to_async

from chat import models
from chat.constants import ACCESS_FULL_CONTEXT, ACCESS_TOOL_CALL_ONLY

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _get_token_encoding():
    """Lazily load and cache the tiktoken encoding."""
    return tiktoken.get_encoding("cl100k_base")


def count_approx_tokens(text: str) -> int:
    """Estimate token count using tiktoken."""
    if not text:
        return 0
    try:
        tiktoken_len = len(_get_token_encoding().encode(text))
        logger.debug("Tiktoken length: %s", tiktoken_len)
        return tiktoken_len
    except Exception:  # pylint: disable=broad-except #noqa: BLE001
        logger.warning("Failed to estimate tokens with tiktoken, falling back to heuristic.")
        non_space_chars = len("".join(text.split()))
        if non_space_chars == 0:
            return 0
        return non_space_chars // 3 + (1 if non_space_chars % 3 else 0)


@sync_to_async
def read_attachment_content(attachment: models.ChatConversationAttachment) -> tuple[str, str]:
    """Read text attachment content from object storage."""
    with default_storage.open(attachment.key) as file:
        return attachment.file_name, file.read().decode("utf-8")


# Keep these literals in sync with chat.constants.ACCESS_* (Literal can't
# reference module-level constants).
Access = Literal["full-context", "tool_call_only"]
DocumentInfoLabel = Literal["first_uploaded_document", "last_uploaded_document"]
TOOL_CALL_ONLY_CONTENT = "available via tools"


@dataclasses.dataclass
class DocumentInfo:
    """LLM-visible shape for one document entry in the listing."""

    document_id: str
    title: str
    access: Access
    content: str | None
    info: DocumentInfoLabel | None = None


@dataclasses.dataclass
class DocumentsListing:
    """LLM-visible shape for the full attached-documents listing."""

    documents: list[DocumentInfo]
    note: str
    documents_order: Literal["newest_to_oldest"] = "newest_to_oldest"


@dataclasses.dataclass
class _DocumentEntry:
    """Internal working state for a document during inlining/eviction.

    Carries the same identity/title fields as DocumentInfo, plus the
    bookkeeping needed by the FIFO policy (token_count, inlineable).
    """

    document_id: str
    title: str
    content: str
    token_count: int
    inlineable: bool
    access: Access = ACCESS_TOOL_CALL_ONLY
    info: DocumentInfoLabel | None = None

    def to_info(self, *, force_tool_call_only: bool) -> DocumentInfo:
        """Project this internal entry to its LLM-visible shape."""
        return DocumentInfo(
            document_id=self.document_id,
            title=self.title,
            access=ACCESS_TOOL_CALL_ONLY if force_tool_call_only else self.access,
            content=None if force_tool_call_only else self.content,
            info=self.info,
        )


def _display_title_from_name(file_name: str | None, is_converted: bool) -> str:
    """Return user-facing title, preserving real markdown filenames."""
    title = file_name or ""
    return title.removesuffix(".md") if is_converted else title


def _build_documents_listing(
    docs: list[_DocumentEntry],
    force_tool_call_only: bool,
) -> DocumentsListing:
    """Build the ordered documents listing (with access note) for the model."""
    note = (
        f"Documents marked '{ACCESS_TOOL_CALL_ONLY}' are accessible through tools like "
        "RAG search or summary. "
    )
    if not force_tool_call_only:
        note += (
            f"Documents marked '{ACCESS_FULL_CONTEXT}' can be directly "
            "manipulated by you, either for referencing, analysis or summarization. "
            f"Do not use a tool to access a document marked '{ACCESS_FULL_CONTEXT}', this is "
            "counterproductive as the content is already available here."
        )
    return DocumentsListing(
        documents=[
            doc.to_info(force_tool_call_only=force_tool_call_only) for doc in reversed(docs)
        ],
        note=note,
    )


def _render_listing(listing: DocumentsListing) -> str:
    """Serialize the listing as the JSON-prefixed instruction snippet."""
    return (
        "List of documents attached to this conversation:\n"
        f"{json.dumps(dataclasses.asdict(listing), ensure_ascii=False, indent=2)}"
    )


def _info_label_for(index: int, total: int) -> DocumentInfoLabel | None:
    """Position label - first wins when there is a single document."""
    if index == 1:
        return "first_uploaded_document"
    if index == total:
        return "last_uploaded_document"
    return None


def _apply_fifo_inlining(
    docs: list[_DocumentEntry],
    document_budget: int,
    conversation_id: str,
) -> list[_DocumentEntry]:
    """Return a new list with access/content updated per FIFO budget policy.

    Inline what fits, evict oldest on overflow; oversize docs stay tool_call_only.
    """
    inlined: set[int] = set()
    inlined_order: deque[int] = deque()
    inlined_total = 0

    for i, doc in enumerate(docs):
        if not doc.inlineable:
            # Failed reads stay tool_call_only and are excluded from budget math.
            continue
        if doc.token_count > document_budget:
            logger.debug(
                "conversation=%s document '%s' (%s tokens) exceeds budget (%s); "
                "keeping tool_call_only.",
                conversation_id,
                doc.title,
                doc.token_count,
                document_budget,
            )
            continue

        while inlined_order and inlined_total + doc.token_count > document_budget:
            evicted_idx = inlined_order.popleft()
            inlined.discard(evicted_idx)
            inlined_total -= docs[evicted_idx].token_count
            logger.debug(
                "conversation=%s evicted document title=%s",
                conversation_id,
                docs[evicted_idx].title,
            )

        if inlined_total + doc.token_count <= document_budget:
            inlined.add(i)
            inlined_order.append(i)
            inlined_total += doc.token_count
            logger.debug(
                "conversation=%s inlined document title=%s",
                conversation_id,
                doc.title,
            )

    result: list[_DocumentEntry] = []
    for i, doc in enumerate(docs):
        if i in inlined:
            result.append(dataclasses.replace(doc, access=ACCESS_FULL_CONTEXT))
        elif doc.inlineable:
            # Inlineable but didn't make the cut (oversize or evicted) - scrub content.
            result.append(dataclasses.replace(doc, content=TOOL_CALL_ONLY_CONTENT))
        else:
            # Failed reads already carry TOOL_CALL_ONLY_CONTENT - pass through.
            result.append(doc)
    return result


async def build_document_context_instruction(  # noqa: PLR0913 # pylint: disable=too-many-arguments,too-many-locals
    *,
    conversation_id: str,
    text_attachments: Sequence[models.ChatConversationAttachment],
    model_hrid: str,
    max_token_context: int | None,
    budget_ratio: float,
    security_buffer_tokens: int,
) -> str:
    """
    Build document instructions with a rolling full-context FIFO window.

    Rules:
    - Reserve a ratio of max model context for full document inclusion.
    - Keep all documents listed with an explicit accessibility status.
    - Apply FIFO eviction on inlined documents when budget is exceeded.
    """
    if not text_attachments:
        return ""

    placeholder_docs = [
        _DocumentEntry(
            document_id=str(attachment.id),
            title=_display_title_from_name(
                attachment.file_name, bool(getattr(attachment, "conversion_from", None))
            ),
            content=TOOL_CALL_ONLY_CONTENT,
            token_count=0,
            inlineable=False,
        )
        for attachment in text_attachments
    ]

    if not max_token_context:
        logger.warning(
            "conversation=%s model='%s' has no max_token_context; skipping full document inlining.",
            conversation_id,
            model_hrid,
        )
        return _render_listing(
            _build_documents_listing(docs=placeholder_docs, force_tool_call_only=True)
        )

    if budget_ratio == 0:
        logger.info(
            "conversation=%s DOCUMENT_CONTEXT_BUDGET_RATIO is 0 for model '%s'; "
            "disabling full document inlining.",
            conversation_id,
            model_hrid,
        )
        return _render_listing(
            _build_documents_listing(docs=placeholder_docs, force_tool_call_only=True)
        )

    document_budget = max(int(max_token_context * budget_ratio) - security_buffer_tokens, 0)

    async def _load_document(
        index: int, attachment: models.ChatConversationAttachment
    ) -> _DocumentEntry:
        try:
            title, content = await read_attachment_content(attachment)
            token_count = count_approx_tokens(content)
            inlineable = True
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "conversation=%s could not inline attachment '%s'; keeping it tool_call_only: %s",
                conversation_id,
                getattr(attachment, "file_name", "<unknown>"),
                exc,
                exc_info=True,
            )
            title = getattr(attachment, "file_name", None)
            content = TOOL_CALL_ONLY_CONTENT
            token_count = 0
            inlineable = False
        return _DocumentEntry(
            document_id=str(getattr(attachment, "id", "")),
            title=_display_title_from_name(
                title, bool(getattr(attachment, "conversion_from", None))
            ),
            content=content,
            token_count=token_count,
            inlineable=inlineable,
            info=_info_label_for(index, len(text_attachments)),
        )

    docs: list[_DocumentEntry] = list(
        await asyncio.gather(
            *(
                _load_document(index, attachment)
                for index, attachment in enumerate(text_attachments, start=1)
            )
        )
    )

    docs = _apply_fifo_inlining(docs, document_budget, conversation_id)
    inlined_total = sum(doc.token_count for doc in docs if doc.access == ACCESS_FULL_CONTEXT)
    inlined_count = sum(1 for doc in docs if doc.access == ACCESS_FULL_CONTEXT)

    filled_ratio = (inlined_total / document_budget) if document_budget else 0
    logger.debug(
        (
            "Document context window usage - conversation=%s model=%s budget_ratio=%s "
            "document_budget_tokens=%s inlined_tokens=%s filled_ratio=%.4f "
            "total_documents=%s inlined_documents=%s"
        ),
        conversation_id,
        model_hrid,
        budget_ratio,
        document_budget,
        inlined_total,
        filled_ratio,
        len(docs),
        inlined_count,
    )

    return _render_listing(_build_documents_listing(docs=docs, force_tool_call_only=False))
