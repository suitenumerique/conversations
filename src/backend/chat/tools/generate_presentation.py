"""Slide deck generation tool for the chat agent."""

import logging
import secrets

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify

from asgiref.sync import sync_to_async
from pydantic import BaseModel, ValidationError
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ToolReturn, ToolReturnPart

from core.file_upload.enums import AttachmentStatus
from core.file_upload.utils import generate_retrieve_policy

from chat import models
from chat.agent_rag.document_converter.guards import guard_zip_bomb
from chat.agents.presentation import PresentationAgent
from chat.constants import PPTX_MIME_TYPE, TEXT_MIME_PREFIX
from chat.file_generation import (
    GENERIC_TEMPLATE,
    Presentation,
    PresentationBuildError,
    PresentationStyle,
    TemplatedPresentation,
    TemplateOutline,
    build_from_template,
    build_presentation,
    outline_template,
)
from chat.tokens import compute_document_budget, count_approx_tokens, truncate_to_tokens
from chat.tools.document_summarize import _summarize_text_attachments, read_document_content
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

# What the deck cannot do yet. Spelled out in the tool result so the model does
# not claim to the user that it was done.
UNSUPPORTED_REQUESTS = "New logos, images, charts and diagrams were NOT added."

# Tools whose result carries a deck that update_presentation can build on.
PRESENTATION_TOOLS = ("generate_presentation", "update_presentation")
PRESENTATION_METADATA_KEY = "presentation"

# Instructions handed to the summarization pipeline when the source documents
# are too long to be given verbatim to the presentation agent.
SOURCE_CONDENSE_INSTRUCTIONS = (
    "This summary will be turned into a slide deck. Keep the structure of the "
    "document (parts and sub-parts), and every key fact, figure, date, name, "
    "recommendation and conclusion. Prefer a long, detailed summary over a short one."
)

SUMMARY_WRAPPER = "<documents_summary>\n{summary}\n</documents_summary>"


class StoredPresentation(BaseModel):
    """
    What is kept of a deck so that a later turn can restyle or edit it.

    It travels in the tool result's metadata, which is persisted with the
    conversation history but never sent to the model.
    """

    presentation: Presentation | TemplatedPresentation
    style: PresentationStyle = PresentationStyle()
    # Storage key of the user's pptx the deck copies its slides from, if any.
    template_key: str = ""
    # The source material the deck was built from, already within the budget,
    # so that an edit reuses it instead of reading and condensing the documents again.
    source_material: str = ""
    source_names: list[str] = []


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
    if document_ids is None:
        return _ready_text_attachments(conversation=conversation)
    candidates = _readable_attachments(conversation)
    # dict.fromkeys drops duplicate ids while keeping the order given.
    return [
        resolve_attachment_by_id(candidates, document_id)
        for document_id in dict.fromkeys(document_ids)
    ]


def _readable_attachments(conversation) -> list:
    """The documents the model may point to: the conversation's, then its project's."""
    attachments = _ready_text_attachments(conversation=conversation)
    if conversation.project_id:
        attachments += _ready_text_attachments(project_id=conversation.project_id)
    return attachments


def _ready_text_attachments(**scope) -> list:
    return list(
        models.ChatConversationAttachment.objects.filter(
            content_type__startswith=TEXT_MIME_PREFIX,
            upload_state=AttachmentStatus.READY,
            **scope,
        ).order_by("created_at", "id")
    )


@sync_to_async
def get_template_key(conversation, template_id: str) -> str:
    """
    Resolve the storage key of the pptx a template id points to.

    The model only sees the Markdown companion of an uploaded pptx, so the id
    is the companion's: the pptx is the attachment it was converted from.
    """
    companion = resolve_attachment_by_id(_readable_attachments(conversation), template_id)
    template = models.ChatConversationAttachment.objects.filter(
        conversation_id=companion.conversation_id,
        project_id=companion.project_id,
        key=companion.conversion_from,
        content_type=PPTX_MIME_TYPE,
    ).first()
    if template is None:
        raise ModelRetry("template_id must point to an attached pptx file.")
    return template.key


@sync_to_async
def read_template(key: str) -> bytes:
    """Read the user's pptx from storage, refusing a decompression bomb."""
    with default_storage.open(key) as file:
        blob = file.read()
    guard_zip_bomb(blob)
    return blob


def _source_budget() -> int:
    """Token budget for source documents in the presentation agent's prompt."""
    configuration = settings.LLM_CONFIGURATIONS[settings.LLM_DEFAULT_MODEL_HRID]
    return compute_document_budget(
        configuration.max_token_context or settings.DEFAULT_MAX_TOKEN_CONTEXT,
        settings.DOCUMENT_CONTEXT_BUDGET_RATIO,
        settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS,
    )


async def build_sources(ctx: RunContext, attachments: list) -> tuple[str, list[str]]:
    """
    Return the source material for the deck, and the names of the documents used.

    Documents are given verbatim when they fit the budget. Longer ones go through
    the summarization pipeline first, asked to keep the details a deck needs, and
    the summary is cut to the budget should it still exceed it. An unreadable
    document is skipped rather than failing the whole deck.
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

    names = [name for name, _content in documents]
    verbatim = "\n\n".join(
        f'<document name="{name}">\n{content}\n</document>' for name, content in documents
    )
    budget = _source_budget()
    if count_approx_tokens(verbatim) <= budget:
        return verbatim, names

    # The wrapping tags count against the budget too.
    summary_budget = budget - count_approx_tokens(SUMMARY_WRAPPER.format(summary=""))
    if summary_budget <= 0:
        # No room for any source material: build the deck from the brief alone
        # rather than citing documents the agent never saw.
        logger.warning("No budget left for source documents in the presentation prompt")
        return "", []

    logger.info("Source documents exceed the presentation budget, condensing them first")
    condensed = await _summarize_text_attachments(
        attachments,
        instructions=SOURCE_CONDENSE_INSTRUCTIONS,
        document_id=None,
        ctx=ctx,
        empty_set_message="No source document could be read.",
    )
    summary = condensed.return_value
    if count_approx_tokens(summary) > summary_budget:
        logger.warning("Condensed sources still exceed the presentation budget, truncating them")
        summary = truncate_to_tokens(summary, summary_budget)
    return SUMMARY_WRAPPER.format(summary=summary), names


def build_agent_prompt(
    brief: str, slide_count: int | None, sources: str, template: TemplateOutline | None
) -> str:
    """Assemble what the presentation agent is asked to turn into a deck."""
    return _prompt_sections(
        ("Brief", brief.strip()),
        (
            "Number of slides",
            f"Exactly {slide_count} slides, cover and section slides included."
            if slide_count
            else None,
        ),
        ("User's slides", template and template.description),
        ("Source documents", sources),
    )


def build_edit_prompt(
    presentation: Presentation | TemplatedPresentation,
    instructions: str,
    sources: str,
    template: TemplateOutline | None,
) -> str:
    """Assemble what the presentation agent is asked to change in an existing deck."""
    return _prompt_sections(
        ("Current deck", presentation.model_dump_json(exclude_defaults=True)),
        ("Changes requested", instructions),
        ("User's slides", template and template.description),
        ("Source documents", sources),
    )


def _prompt_sections(*sections: tuple[str, str | None]) -> str:
    """Join the non-empty ``(heading, body)`` sections of a prompt."""
    return "\n\n".join(f"## {heading}\n\n{body}" for heading, body in sections if body)


def find_presentations(ctx: RunContext) -> list[StoredPresentation]:
    """
    Return the decks generated or updated in the conversation, oldest first.

    Earlier turns are read from the persisted history, since the history the
    agent runs on has their tool results compacted, metadata included. Results
    of the current turn are only in the run's own messages.
    """
    persisted = [
        part
        for message in ctx.deps.conversation.pydantic_messages or []
        for part in message.get("parts", [])
        if part.get("part_kind") == "tool-return" and part.get("tool_name") in PRESENTATION_TOOLS
    ]
    persisted_call_ids = {part.get("tool_call_id") for part in persisted}
    metadatas = [part.get("metadata") for part in persisted] + [
        part.metadata
        for message in ctx.messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
        and part.tool_name in PRESENTATION_TOOLS
        and part.tool_call_id not in persisted_call_ids
    ]

    decks = []
    for metadata in metadatas:
        if not metadata or PRESENTATION_METADATA_KEY not in metadata:
            continue
        try:
            decks.append(StoredPresentation.model_validate(metadata[PRESENTATION_METADATA_KEY]))
        except ValidationError:
            logger.warning("Skipping an unreadable stored presentation", exc_info=True)
    return decks


def charts_note(
    presentation: Presentation | TemplatedPresentation, template: TemplateOutline | None
) -> str:
    """Tell the model which slides copy a chart of the user's, whose data was not updated."""
    if template is None or not (slides := template.copied_charts(presentation)):
        return ""
    return (
        f" Slides {', '.join(map(str, slides))} copy a chart of the user's pptx with its "
        "original data: tell the user it was not updated."
    )


async def load_template_outline(key: str) -> TemplateOutline:
    """Describe the user's slides for the presentation agent."""
    try:
        return await sync_to_async(outline_template)(await read_template(key))
    except Exception as exc:
        logger.warning("Failed to read the presentation template %s", key, exc_info=True)
        raise ModelCannotRetry(
            "The user's pptx could not be read as a template: it may have been deleted "
            "or be damaged. You must explain this to the user."
        ) from exc


async def run_presentation_agent(
    ctx: RunContext,
    prompt: str,
    slide_count: int | None = None,
    template: TemplateOutline | None = None,
) -> Presentation | TemplatedPresentation:
    """Have the presentation agent write the deck described by ``prompt``."""
    try:
        agent = PresentationAgent(slide_count=slide_count, template=template)
        result = await agent.run(prompt, usage=ctx.usage)
    except AgentRunError as exc:
        # The agent itself failed (model API/HTTP error, unexpected model
        # behaviour, usage limit): a retry may recover, so let the model try.
        logger.warning("Presentation agent failed: %s", exc, exc_info=True)
        raise ModelRetry("The presentation outline could not be produced.") from exc
    except Exception as exc:
        # Anything else is a server-side bug, not something a retry fixes.
        logger.exception("Unexpected error while producing the presentation outline")
        raise ModelCannotRetry("The presentation outline could not be produced.") from exc
    return result.output


async def save_presentation(
    ctx: RunContext, stored: StoredPresentation, headline: str
) -> ToolReturn:
    """Build and store the deck, and tell the model how to hand it to the user."""
    presentation = stored.presentation
    try:
        if stored.template_key:
            template = await read_template(stored.template_key)
            blob = await sync_to_async(build_from_template)(template, presentation, stored.style)
        else:
            blob = await sync_to_async(build_presentation)(
                GENERIC_TEMPLATE, presentation, stored.style
            )
    except Exception as exc:
        # Neither is something a different brief would fix: the bundled template
        # failing is a deployment problem, the user's one a pptx we cannot use.
        logger.exception("Failed to build the presentation")
        reason = (
            "the user's pptx could not be used as a template"
            if stored.template_key
            else "of a server-side error"
        )
        raise ModelCannotRetry(
            f"The presentation could not be generated because {reason}."
        ) from exc

    try:
        url = await store_presentation(ctx.deps.conversation, presentation.title, blob)
    except Exception as exc:
        logger.exception("Failed to store the generated presentation")
        raise ModelCannotRetry("The presentation was generated but could not be saved.") from exc

    logger.info(
        "Saved presentation (%d slides, %d sources) for conversation %s",
        len(presentation.slides),
        len(stored.source_names),
        ctx.deps.conversation.pk,
    )

    return ToolReturn(
        return_value=(
            f"{headline} Give the user this temporary download link: {url} — do not "
            "restate the deck's content.\n"
            f"Limitations: {UNSUPPORTED_REQUESTS} If the user asked for any of "
            "these, tell them plainly that it was not applied; never claim otherwise."
        ),
        metadata={
            "url": url,
            "sources": stored.source_names,
            PRESENTATION_METADATA_KEY: stored.model_dump(mode="json"),
        },
    )


@last_model_retry_soft_fail
async def generate_presentation(  # noqa: PLR0913 # pylint: disable=too-many-arguments
    ctx: RunContext,
    *,
    brief: str,
    slide_count: int | None = None,
    document_ids: list[str] | None = None,
    style: PresentationStyle | None = None,
    template_id: str | None = None,
) -> ToolReturn:
    """
    Generate a slide deck and return a link to download it.

    Args:
        brief: What the deck must cover, in the user's own terms. Include the
            subject, the audience, the plan or structure, the key points and the
            level of detail the user asked for.
        slide_count: The total number of slides the user asked for, if they
            gave one. Leave empty otherwise.
        document_ids: UUIDs of the documents to build the deck from, taken from
            the `documents` or `project_documents` context arrays. Leave empty
            to use every document attached to the conversation, or pass an
            empty list to use none. Do not include a pptx template the user
            attached as a model to follow: only content sources.
        style: The colours, fonts and text sizes the user asked for, if any.
        template_id: UUID of an attached pptx, taken from the `documents` or
            `project_documents` context arrays, when the user wants the deck
            built on it: as a template, a model, or a deck to start from.

    Returns:
        ToolReturn: confirmation carrying the download link.
    """
    if not brief.strip():
        raise ModelRetry("The brief is empty. Describe what the presentation must cover.")
    if slide_count is not None and slide_count < 1:
        raise ModelRetry("slide_count must be a positive number, or left empty.")

    template_key, template = "", None
    if template_id:
        template_key = await get_template_key(ctx.deps.conversation, template_id)
        template = await load_template_outline(template_key)

    attachments = [
        attachment
        for attachment in await get_source_attachments(ctx.deps.conversation, document_ids)
        if str(attachment.id) != template_id
    ]
    try:
        sources, source_names = await build_sources(ctx, attachments)
    except ModelRetry, ModelCannotRetry:
        raise
    except Exception as exc:
        logger.exception("Unexpected error while preparing the presentation sources")
        raise ModelCannotRetry("The source documents could not be prepared.") from exc

    presentation = await run_presentation_agent(
        ctx, build_agent_prompt(brief, slide_count, sources, template), slide_count, template
    )

    template_note = ", out of the slides of the user's pptx" if template_key else ""
    sources_note = (
        f"It was built from: {', '.join(source_names)}."
        if source_names
        else "It was built from the brief only, without any source document."
    )
    return await save_presentation(
        ctx,
        StoredPresentation(
            presentation=presentation,
            style=style or PresentationStyle(),
            source_material=sources,
            source_names=source_names,
            template_key=template_key,
        ),
        f"The presentation '{presentation.title}' was generated with "
        f"{len(presentation.slides)} slides{template_note}. {sources_note}"
        f"{charts_note(presentation, template)}",
    )


@last_model_retry_soft_fail
async def update_presentation(
    ctx: RunContext,
    instructions: str | None = None,
    style: PresentationStyle | None = None,
    revert: bool = False,
) -> ToolReturn:
    """
    Restyle, edit or revert the last presentation of the conversation, as a new version.

    Args:
        instructions: The content or layout changes the user asked for, in
            their own terms (e.g. "expand slide 4", "put slide 3 on two
            columns"). Leave empty for a style-only change.
        style: The style changes the user asked for. Only set the fields they
            want changed: the others keep their current value.
        revert: Set when the user asks to undo the last change: the previous
            version is restored exactly as it was, ignoring instructions and style.

    Returns:
        ToolReturn: confirmation carrying the download link.
    """
    instructions = (instructions or "").strip()
    if not instructions and style is None and not revert:
        raise ModelRetry("Nothing to change: give instructions, a style, or revert.")

    decks = find_presentations(ctx)
    if not decks:
        raise ModelCannotRetry(
            "There is no presentation to update in this conversation: generate one "
            "with generate_presentation instead."
        )
    if revert:
        if len(decks) < 2:
            raise ModelCannotRetry("The presentation has no earlier version to restore.")
        previous = decks[-2]
        return await save_presentation(
            ctx,
            previous,
            f"The presentation '{previous.presentation.title}' was restored to its "
            "previous version, exactly as it was.",
        )

    stored = decks[-1]
    presentation, template = stored.presentation, None
    if instructions:
        # Content changes go through the agent, with the deck's sources so that
        # what it adds comes from them. A style-only change keeps the content
        # word for word.
        if stored.template_key:
            template = await load_template_outline(stored.template_key)
        presentation = await run_presentation_agent(
            ctx,
            build_edit_prompt(presentation, instructions, stored.source_material, template),
            template=template,
        )

    updated = stored.model_copy(
        update={
            "presentation": presentation,
            "style": stored.style.updated_with(style) if style else stored.style,
        }
    )
    return await save_presentation(
        ctx,
        updated,
        f"The presentation '{presentation.title}' was updated and now has "
        f"{len(presentation.slides)} slides.{charts_note(presentation, template)}",
    )
