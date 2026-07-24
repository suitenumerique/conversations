"""Slide deck generation tool for the chat agent."""

import logging
import secrets

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import slugify

from asgiref.sync import sync_to_async
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ToolReturn

from core.file_upload.utils import generate_retrieve_policy

from chat.agents.presentation import PresentationAgent
from chat.file_generation import GENERIC_TEMPLATE, PresentationBuildError, build_presentation
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail

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


@last_model_retry_soft_fail
async def generate_presentation(ctx: RunContext, brief: str) -> ToolReturn:
    """
    Generate a slide deck and return a link to download it.

    Args:
        brief: What the deck must cover, in the user's own terms. Include the
            subject, the audience and any structure the user asked for.

    Returns:
        ToolReturn: confirmation carrying the download link.
    """
    if not brief.strip():
        raise ModelRetry("The brief is empty. Describe what the presentation must cover.")

    try:
        result = await PresentationAgent().run(brief, usage=ctx.usage)
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
        "Generated presentation (%d slides) for conversation %s",
        len(presentation.slides),
        ctx.deps.conversation.pk,
    )

    return ToolReturn(
        return_value=(
            f"The presentation '{presentation.title}' was generated with "
            f"{len(presentation.slides)} slides. Give the user this temporary "
            f"download link: {url} — do not restate the deck's content."
        ),
        metadata={"url": url},
    )
