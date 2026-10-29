"""Slide deck generation tool for the chat agent."""

import html
import logging
import re
import secrets

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify

from asgiref.sync import sync_to_async
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ToolReturn

from core.file_upload.enums import AttachmentStatus
from core.file_upload.utils import generate_retrieve_policy

from chat import models
from chat.agents.presentation import PresentationAgent
from chat.constants import TEXT_MIME_PREFIX
from chat.file_generation import GENERIC_TEMPLATE, PresentationBuildError, build_presentation
from chat.tokens import compute_document_budget, count_approx_tokens, truncate_to_tokens
from chat.tools.document_summarize import _summarize_documents, read_document_content
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail, resolve_attachment_by_id

logger = logging.getLogger(__name__)

PPTX_EXTENSION = "pptx"

# Generated decks are ephemeral, one-off artifacts with no attachment row to back
# them, so they live under a dedicated prefix rather than the durable
# ``attachments/`` folder. This lets a storage lifecycle rule expire objects under
# ``<conversation>/generated/`` without ever touching real attachments; configure
# such a rule on the bucket, as nothing else prunes these objects.
GENERATED_FOLDER = "generated"

# Cap the readable part of the file name so long titles stay manageable.
MAX_NAME_LENGTH = 60

# Lifetime of the download link. Longer than the default retrieve policy, which
# is tuned for URLs the LLM reads at once: this one is for a user to click.
DOWNLOAD_URL_EXPIRATION = 15 * 60  # 15 minutes

# Beyond this, a deck no longer fits the agent's output and keeps failing the
# slide count check.
MAX_SLIDE_COUNT = 50

# What the deck cannot do yet. Spelled out in the tool result so the model does
# not claim to the user that a template or a style instruction was honoured.
UNSUPPORTED_REQUESTS = (
    "The deck always uses the standard template: an attached pptx template or "
    "slide master, requested colours, fonts, font sizes, logos, images, charts "
    "and diagrams were NOT applied."
)

# Instructions handed to the summarization pipeline when the source documents
# are too long to be given verbatim to the presentation agent.
SOURCE_CONDENSE_INSTRUCTIONS = (
    "This summary will be turned into a slide deck. Keep the structure of the "
    "document (parts and sub-parts), and every key fact, figure, date, name, "
    "recommendation and conclusion. Prefer a long, detailed summary over a short one."
)

SUMMARY_WRAPPER = "<documents_summary>\n{summary}\n</documents_summary>"

# Matches `</document>` and `</documents_summary>`, the tags wrapping the sources.
CLOSING_TAG_PATTERN = re.compile(r"</(document)", re.IGNORECASE)


def build_object_name(title: str) -> str:
    """
    Build a readable, non-guessable file name from the deck title.

    Shaped as ``<snake_case_title>_<hex>.pptx``: the slug is what the user sees
    when downloading (the presigned URL exposes the key's last segment), and the
    random hex keeps the object key from being guessable.
    """
    slug = slugify(title).replace("-", "_")[:MAX_NAME_LENGTH].strip("_") or "presentation"
    return f"{slug}_{secrets.token_hex(4)}.{PPTX_EXTENSION}"


@sync_to_async
def store_presentation(conversation, title: str, blob: bytes) -> str:
    """
    Write the deck to object storage and return a presigned URL to download it.

    The deck is a one-off artifact, so no attachment row is created: it is
    reachable through a signed, time-limited URL rather than a durable record.
    The key is scoped to the conversation to keep the artifact tied to it, under
    the ``generated`` prefix so a lifecycle rule can prune it (see GENERATED_FOLDER).
    """
    key = f"{conversation.pk}/{GENERATED_FOLDER}/{build_object_name(title)}"
    # The last segment is a slug, not a UUID, so this key does NOT match
    # AttachmentMixin.MEDIA_STORAGE_URL_PATTERN and cannot be served through the
    # cookie-authenticated media proxy: the deck is reached only via the
    # presigned URL returned below. Route it through the proxy and it would 403.
    #
    # Storage may hand back a different name than requested (S3 is configured
    # with AWS_S3_FILE_OVERWRITE=False), so sign the key that was written.
    key = default_storage.save(key, ContentFile(blob))

    return generate_retrieve_policy(key, expiration=DOWNLOAD_URL_EXPIRATION)


@sync_to_async
def get_source_attachments(conversation, document_ids: list[str] | None) -> list:
    """
    Resolve the text documents the deck is built from.

    With no ``document_ids``, every document of the conversation is used. Ids
    may also target project-library files. Only READY attachments are eligible,
    matching the documents listing the model picks its ids from.
    """
    conversation_documents = list(
        conversation.attachments.filter(
            content_type__startswith=TEXT_MIME_PREFIX,
            upload_state=AttachmentStatus.READY,
        ).order_by("created_at", "id")
    )
    if document_ids is None:
        return conversation_documents

    candidates = conversation_documents
    if conversation.project_id:
        candidates += list(
            models.ChatConversationAttachment.objects.filter(
                project_id=conversation.project_id,
                content_type__startswith=TEXT_MIME_PREFIX,
                upload_state=AttachmentStatus.READY,
            ).order_by("created_at", "id")
        )
    # dict.fromkeys drops duplicate ids while keeping the order given.
    return [
        resolve_attachment_by_id(candidates, document_id)
        for document_id in dict.fromkeys(document_ids)
    ]


def _source_budget() -> int:
    """Token budget for source documents in the presentation agent's prompt."""
    configuration = settings.LLM_CONFIGURATIONS[settings.LLM_DEFAULT_MODEL_HRID]
    return compute_document_budget(
        configuration.max_token_context or settings.DEFAULT_MAX_TOKEN_CONTEXT,
        settings.DOCUMENT_CONTEXT_BUDGET_RATIO,
        settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS,
    )


def _escape_closing_tags(text: str) -> str:
    """Stop source text from closing the tags that wrap it in the agent's prompt."""
    return CLOSING_TAG_PATTERN.sub(r"&lt;/\1", text)


async def build_sources(ctx: RunContext, attachments: list) -> tuple[str, list[str]]:
    """
    Return the source material for the deck, and the names of the documents used.

    Documents are given verbatim when they all fit the budget. Otherwise, those
    within their fair share of the budget stay verbatim and the longer ones go
    through the summarization pipeline, asked to keep the details a deck needs;
    the summary is cut to the remaining budget should it still exceed it. An
    unreadable document is skipped rather than failing the whole deck.
    """
    documents = []
    for attachment in attachments:
        try:
            documents.append(await read_document_content(attachment))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to read source document %s for a presentation",
                attachment.id,
                exc_info=True,
            )
    if not documents:
        return "", []

    blocks = [
        f'<document name="{html.escape(name)}">\n{_escape_closing_tags(content)}\n</document>'
        for name, content in documents
    ]
    budget = _source_budget()
    verbatim = "\n\n".join(blocks)
    if count_approx_tokens(verbatim) <= budget:
        return verbatim, [name for name, _content in documents]

    share = budget // len(documents)
    kept, kept_names, too_long = [], [], []
    for document, block in zip(documents, blocks, strict=True):
        if count_approx_tokens(block) <= share:
            kept.append(block)
            kept_names.append(document[0])
        else:
            too_long.append(document)

    # The verbatim documents and the wrapping tags count against the budget too.
    summary_budget = (
        budget
        - count_approx_tokens("\n\n".join([*kept, ""]))
        - count_approx_tokens(SUMMARY_WRAPPER.format(summary=""))
    )
    if summary_budget <= 0:
        # No room left to summarize the long documents: leave them out rather
        # than citing documents the agent never saw.
        logger.warning("No budget left for long source documents in the presentation prompt")
        return "\n\n".join(kept), kept_names

    logger.info("Source documents exceed the presentation budget, condensing the long ones")
    summary = _escape_closing_tags(
        await _summarize_documents(too_long, instructions=SOURCE_CONDENSE_INSTRUCTIONS, ctx=ctx)
    )
    if count_approx_tokens(summary) > summary_budget:
        logger.warning("Condensed sources still exceed the presentation budget, truncating them")
        summary = truncate_to_tokens(summary, summary_budget)
    return (
        "\n\n".join([*kept, SUMMARY_WRAPPER.format(summary=summary)]),
        kept_names + [name for name, _content in too_long],
    )


def build_agent_prompt(brief: str, slide_count: int | None, sources: str) -> str:
    """Assemble what the presentation agent is asked to turn into a deck."""
    parts = [f"## Brief\n\n{brief.strip()}"]
    if slide_count is not None:
        parts.append(
            f"## Number of slides\n\nExactly {slide_count} slides, "
            "cover and section slides included."
        )
    if sources:
        parts.append(f"## Source documents\n\n{sources}")
    return "\n\n".join(parts)


@last_model_retry_soft_fail
async def generate_presentation(
    ctx: RunContext,
    brief: str,
    slide_count: int | None = None,
    document_ids: list[str] | None = None,
) -> ToolReturn:
    """
    Generate a slide deck and return a link to download it.

    Args:
        brief: What the deck must cover, in the user's own terms. Include the
            subject, the audience, the plan or structure, the key points and the
            level of detail the user asked for.
        slide_count: The total number of slides the user asked for, if they
            gave one, at most 50. Leave empty otherwise.
        document_ids: UUIDs of the documents to build the deck from, taken from
            the `documents` or `project_documents` context arrays. Omit it
            (null) to use every document attached to the conversation. Pass an
            empty list `[]` only to build the deck from the brief alone. Do not
            include a pptx template the user attached as a model to follow:
            only content sources.

    Returns:
        ToolReturn: confirmation carrying the download link.
    """
    if not brief.strip():
        raise ModelRetry("The brief is empty. Describe what the presentation must cover.")
    if slide_count is not None and not 1 <= slide_count <= MAX_SLIDE_COUNT:
        raise ModelRetry(
            f"slide_count must be between 1 and {MAX_SLIDE_COUNT}, or left empty. "
            "If the user asked for more slides, tell them about this limit."
        )

    attachments = await get_source_attachments(ctx.deps.conversation, document_ids)
    try:
        sources, source_names = await build_sources(ctx, attachments)
    except ModelRetry, ModelCannotRetry:
        raise
    except Exception as exc:
        logger.exception("Unexpected error while preparing the presentation sources")
        raise ModelCannotRetry("The source documents could not be prepared.") from exc

    try:
        result = await PresentationAgent(slide_count=slide_count).run(
            build_agent_prompt(brief, slide_count, sources), usage=ctx.usage
        )
    except AgentRunError as exc:
        # The agent itself failed (model API/HTTP error, unexpected model
        # behaviour, usage limit): a retry may recover, so let the model try.
        logger.warning("Presentation agent failed: %s", exc, exc_info=True)
        raise ModelRetry("The presentation outline could not be produced.") from exc
    except Exception as exc:
        # Anything else is a server-side bug, not something a retry fixes.
        logger.exception("Unexpected error while producing the presentation outline")
        raise ModelCannotRetry("The presentation outline could not be produced.") from exc

    presentation = result.output

    try:
        blob = await sync_to_async(build_presentation)(GENERIC_TEMPLATE, presentation)
    except PresentationBuildError as exc:
        # The template is bundled with the application: a failure here is a
        # deployment problem, not something a different brief would fix.
        logger.exception("Failed to build the presentation")
        raise ModelCannotRetry(
            "The presentation could not be generated because of a server-side error."
        ) from exc

    try:
        url = await store_presentation(ctx.deps.conversation, presentation.title, blob)
    except Exception as exc:
        logger.exception("Failed to store the generated presentation")
        raise ModelCannotRetry("The presentation was generated but could not be saved.") from exc

    logger.info(
        "Generated presentation (%d slides, %d sources) for conversation %s",
        len(presentation.slides),
        len(source_names),
        ctx.deps.conversation.pk,
    )

    sources_note = (
        f"It was built from: {', '.join(source_names)}."
        if source_names
        else "It was built from the brief only, without any source document."
    )
    return ToolReturn(
        return_value=(
            f"The presentation '{presentation.title}' was generated with "
            f"{len(presentation.slides)} slides. {sources_note} Give the user this "
            f"temporary download link: {url} — do not restate the deck's content.\n"
            f"Limitations: {UNSUPPORTED_REQUESTS} If the user asked for any of "
            "these, tell them plainly that it was not applied; never claim otherwise."
        ),
        metadata={"url": url, "sources": source_names},
    )
