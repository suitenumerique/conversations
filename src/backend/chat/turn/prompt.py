"""What a turn sends the model: the prompt, its attachments and the history."""

import dataclasses
import logging
from typing import List, Optional, Tuple

from django.db import transaction

from asgiref.sync import sync_to_async
from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ThinkingPart,
)
from pydantic_ai.models import Model, infer_model_profile

from chat import models
from chat.agents.conversation import ConversationAgent
from chat.agents.local_media_url_processors import (
    build_project_image_urls,
    project_has_image_attachments,
    update_history_local_urls,
    update_local_urls,
)
from chat.ai_sdk_types import FileUIPart, UIMessage
from chat.clients.pydantic_ui_message_converter import ui_message_to_user_content
from chat.clients.schema import ImagePostRunActions
from chat.constants import IMAGE_MIME_PREFIX, TEXT_MIME_PREFIX
from chat.turn.trail import TurnTrail

# Not __name__: "chat.turn.*" would nest under the "chat.turn" turn-trace
# logger, whose level and log filter are meant to cover the turn trace alone.
# Keep the name these lines had before the split.
logger = logging.getLogger("chat.clients.pydantic_ai")

# Stream-protocol contract with the frontend. Mirrored in
# ``useChat.tsx`` (``IMAGES_SKIPPED_EVENT_TYPE`` /
# ``IMAGE_SKIP_REASON_TEXT_ONLY``). Keep both sides in sync when adding new
# reasons or events.
IMAGES_SKIPPED_EVENT_TYPE = "images_skipped"
IMAGE_SKIP_REASON_TEXT_ONLY = "model_text_only"

# Stands in for the answer a turn cut off at the output token limit never wrote, so
# the question it was asked is not replayed as a second user message in a row.
TRUNCATED_TURN_FILLER = "[cut off: output token limit reached]"


@dataclasses.dataclass(frozen=True)
class TurnInputs:
    """Everything the turn needs from its request before anything slow runs.

    Attributes:
        user_prompt: The text content of the user's message.
        input_images: Images to send to the model, presigned, project pins last.
        input_documents: Documents to parse and store.
        image_actions: Image-URL surgery for what gets persisted (see
            ``ImagePostRunActions``).
        history: Validated message history for the agent.
        conversation_has_own_documents: Whether this conversation has its own
            (non-project) text attachments.
        pre_stream_events: Data events to stream before the model is called
            (e.g. images-skipped notices).
    """

    user_prompt: str
    input_images: List
    input_documents: List
    image_actions: ImagePostRunActions
    history: List[ModelMessage]
    conversation_has_own_documents: bool
    pre_stream_events: List[dict]


async def prepare_turn_inputs(
    messages: List[UIMessage],
    *,
    conversation: models.ChatConversation,
    agent: ConversationAgent,
    trail: TurnTrail,
    document_upload_enabled: bool,
) -> TurnInputs:
    """
    Prepare all inputs needed before running the agent.

    This handles the setup phase before the agent iteration loop:
    1. Loads and validates conversation history from pydantic_messages
    2. Pre-signs URLs for any local images in history (S3 signed URLs)
    3. Infers whether the model supports thinking and strips ThinkingPart if not
    4. Extracts user prompt, images, and documents from the last message
    5. Pre-signs URLs for input images
    6. Checks if conversation already has documents in the vector store
    """
    history = _load_history(conversation, agent)

    user_prompt, input_images, input_documents = split_prompt(messages[-1])

    # If the resolved model can't accept images, the model still receives them
    # but ignores them (these endpoints tolerate image parts), and we instruct
    # it to say so. We keep the images in the payload so they persist to history
    # and a later turn on a vision-capable model can read them. We also mark each
    # image attachment on the persisted user message so the frontend can render
    # an inline "image ignored" chip naming the file.
    pre_stream_events: List[dict] = []
    model_supports_image = agent.configuration.supports_image
    ignored_images = []
    if not model_supports_image:
        image_names = list_images(messages)
        ignored_images += image_names
        if await project_has_image_attachments(conversation.project_id):
            ignored_images += ["images in the current project"]
        if ignored_images:
            # Single chat-wide notice: any image (project or history) is
            # ignored by this text-only model.
            pre_stream_events.append(
                {
                    "type": IMAGES_SKIPPED_EVENT_TYPE,
                    "kind": "chat_notice",
                    "reason": IMAGE_SKIP_REASON_TEXT_ONLY,
                }
            )

    if ignored_images:
        logger.info(
            "Model %s cannot read images; instructing it to ignore %d image(s) on conversation %s",
            agent.configuration.hrid,
            len(input_images),
            conversation.pk,
        )
        add_unreadable_images_instruction(agent, ", ".join(ignored_images))
        if mark_image_attachments_skipped(messages[-1]):
            await persist_user_message_for_image_skip(conversation, trail, messages[-1])
            pre_stream_events.append(
                {
                    "type": IMAGES_SKIPPED_EVENT_TYPE,
                    "kind": "last_message_marked",
                    "reason": IMAGE_SKIP_REASON_TEXT_ONLY,
                }
            )

    image_actions = ImagePostRunActions()
    if input_images:
        # presign URLs for local images
        input_images = update_local_urls(
            conversation, input_images, updated_url=image_actions.rewrite
        )

    # Pin every project image to the prompt so vision-capable models see them
    # on every turn, the same way conversation-attached images do. Project
    # images go AFTER conversation-message images: provider hard caps
    # (Anthropic ~20 images/request, OpenAI varies) clip the trailing entries
    # first, so a pinned-library overflow never displaces a user's in-message
    # image. Their presigned URLs land in `image_actions.drop` so the
    # finalize/persistence path strips them from `new_messages` before
    # writing to history - otherwise every turn would accumulate them in
    # `pydantic_messages` and replay them on every reload.
    if model_supports_image:
        project_image_urls = await build_project_image_urls(conversation.project_id)
        if project_image_urls:
            input_images = list(input_images) + project_image_urls
            image_actions.drop.update(img.url for img in project_image_urls)

    conversation_has_own_documents = document_upload_enabled and (
        await _conversation_has_own_documents(conversation)
    )
    return TurnInputs(
        user_prompt=user_prompt,
        input_images=input_images,
        input_documents=input_documents,
        image_actions=image_actions,
        history=history,
        conversation_has_own_documents=conversation_has_own_documents,
        pre_stream_events=pre_stream_events,
    )


def _load_history(
    conversation: models.ChatConversation, agent: ConversationAgent
) -> list[ModelMessage]:
    """The conversation's history, local image URLs presigned, thinking parts
    stripped when the model does not support thinking."""
    history = ModelMessagesTypeAdapter.validate_python(conversation.pydantic_messages)
    history = update_history_local_urls(conversation, history)  # presign URLs for local images

    model = agent.model
    if isinstance(model, Model):
        model_supports_thinking = model.profile.get("supports_thinking")
    else:
        model_supports_thinking = infer_model_profile(model).get("supports_thinking")
    if not model_supports_thinking:
        history = strip_thinking_parts(history)
    return history


async def _conversation_has_own_documents(conversation: models.ChatConversation) -> bool:
    """Whether the conversation has documents of its own in the vector store."""
    return bool(conversation.collection_id) or bool(
        await models.ChatConversationAttachment.objects.filter(
            conversation=conversation,
            content_type__startswith=TEXT_MIME_PREFIX,
            upload_state=models.AttachmentStatus.READY,
        ).aexists()
    )


def split_prompt(
    message: UIMessage,
) -> Tuple[str, List[BinaryContent | ImageUrl], List[BinaryContent]]:
    """
    Prepare the user prompt for the agent.

    This function is used to convert a UIMessage into a format suitable for the agent.
    It extracts the user content from the message and returns it as a list of UserContent.
    """
    user_content = ui_message_to_user_content(message)

    buckets: dict[str, list] = {
        "text": [],
        "image": [],
        "document": [],
        "audio": [],
        "video": [],
    }
    for content in user_content:
        buckets[_content_kind(content)].append(content)
    user_prompt = buckets["text"]
    attachment_images = buckets["image"]
    attachment_documents = buckets["document"]
    attachment_audio = buckets["audio"]
    attachment_video = buckets["video"]

    if attachment_audio:
        # Should be handled by the frontend, but just in case
        raise ValueError("Audio attachments are not supported in the current implementation.")
    if attachment_video:
        # Should be handled by the frontend, but just in case
        raise ValueError("Video attachments are not supported in the current implementation.")

    if len(user_prompt) != 1:
        raise ValueError(
            "User prompt must contain exactly one text part, "
            f"but got {len(user_prompt)} parts: {user_prompt}"
        )

    return user_prompt[0], attachment_images, attachment_documents


def _content_kind(content) -> str:  # noqa: PLR0911  # pylint: disable=too-many-return-statements
    """Which `split_prompt` bucket a piece of user content goes in."""
    if isinstance(content, str):
        return "text"
    if isinstance(content, BinaryContent):
        if content.is_audio:
            return "audio"
        if content.is_video:
            return "video"
        if content.is_image:
            return "image"
        return "document"
    if isinstance(content, ImageUrl):
        return "image"
    if isinstance(content, DocumentUrl):
        return "document"
    # Should never happen, but just in case
    raise ValueError(f"Unsupported UserContent type: {type(content)}")


def strip_thinking_parts(history: list[ModelMessage]) -> list[ModelMessage]:
    """Remove ThinkingPart from ModelResponse history for models that don't support it.

    Some models (e.g. mistral-medium) reject requests when previous assistant
    messages contain ThinkingPart. This strips those parts before the history
    is passed to the agent.

    Only called when the current model's pydantic-ai ModelProfile.supports_thinking is False.
    (no thinking_tags and no openai_supports_encrypted_reasoning_content).
    """
    has_thinking = any(
        isinstance(p, ThinkingPart)
        for msg in history
        if isinstance(msg, ModelResponse)
        for p in msg.parts
    )
    if not has_thinking:
        return history

    result = []
    for original_message in history:
        message = original_message
        if isinstance(message, ModelResponse) and any(
            isinstance(p, ThinkingPart) for p in message.parts
        ):
            message = dataclasses.replace(
                message, parts=[p for p in message.parts if not isinstance(p, ThinkingPart)]
            )
        result.append(message)
    return result


def iter_image_attachments(messages: list[UIMessage]):
    """Yield each image-like file part across the given messages.

    Single source of truth for the "is this attachment an image?" predicate
    used by readers (``list_images``) and writers (``mark_image_attachments_skipped``).
    """
    for message in messages:
        for part in message.parts or []:
            if isinstance(part, FileUIPart) and (part.mediaType or "").startswith(
                IMAGE_MIME_PREFIX
            ):
                yield part


def list_images(messages: list[UIMessage]) -> list[str]:
    """Return names of every image attachment across the message history."""
    return [part.filename for part in iter_image_attachments(messages) if part.filename]


def mark_image_attachments_skipped(user_message: UIMessage) -> bool:
    """Stamp a ``skipped`` marker on every image-like file part.

    Returns True if at least one attachment was marked. The persisted user
    bubble keeps the image attachments (filenames + URLs) so the frontend
    can render a "removed: model can't read images" chip on reload; we just
    flag each so renderers know not to fetch the image and to show the chip
    instead of the thumbnail.
    """
    marked = False
    for attachment in iter_image_attachments([user_message]):
        if attachment.skipped is None:
            attachment.skipped = {"reason": IMAGE_SKIP_REASON_TEXT_ONLY}
            marked = True
    return marked


async def persist_user_message_for_image_skip(
    conversation: models.ChatConversation, trail: TurnTrail, user_message: UIMessage
) -> None:
    """Persist the inbound user message early so it carries the skipped marker.

    ``prepare_update_conversation`` normally rebuilds the user bubble from
    the agent's final_output; that path silently drops attachments the agent
    never saw (because we stripped them), losing the filenames the frontend
    needs to render the "image removed" chip. By saving the original message
    here (with markers already stamped), the rebuild step short-circuits on
    ``TurnTrail.question_stored`` and the marked version stands.

    Guarded on that flag rather than on a trailing user message: a
    question-only turn folded in earlier leaves one too, and reading it as
    "already stored" skipped the markers this exists to keep.
    """
    if trail.question_stored:
        return

    def store():
        with transaction.atomic():
            # Re-read under a lock: a turn running in another tab may have
            # landed since this one loaded the conversation, and appending
            # to the stale copy would erase it.
            conversation.refresh_from_db(
                from_queryset=models.ChatConversation.objects.select_for_update(),
                fields=["messages"],
            )
            conversation.messages = list(conversation.messages) + [user_message]
            conversation.save(update_fields=["messages"])

    await sync_to_async(store)()
    trail.question_stored = True


def add_unreadable_images_instruction(agent: ConversationAgent, subject: Optional[str]) -> None:
    """Tell a text-only model an image is present that it cannot read.

    The model receives the image parts but ignores them; this instruction makes
    it aware an image was provided so it can say it can't read images rather than
    answer obliviously. ``subject`` names the image(s), e.g. ``"sample.png"`` or
    ``"an image in the current project"``.
    """

    @agent.instructions
    def acknowledge_unreadable_images() -> str:
        """Instruct the model to tell the user it cannot read attached images."""
        return (
            f"This conversation includes {subject or 'some images'}, but you cannot read or "
            "process images. If a request depends on it, tell the user you "
            "can't read images."
        )


def append_filler_after_dangling_request(history: list[ModelMessage]) -> None:
    """Keep replayed history alternating: Mistral rejects the same role twice.

    A stored turn can end on a request with no response after it, and the next
    turn's prompt would then follow it as a second message in the same role:
    a tool return (`Unexpected role 'user' after role 'tool'`), or a question
    a turn cut off at the output token limit never got to answer.
    """
    if not (history and history[-1].kind == "request" and history[-1].parts):
        return
    _last_part_kind = history[-1].parts[-1].part_kind
    if _last_part_kind == "tool-return":
        history.append(ModelResponse(parts=[TextPart(content="ok")], kind="response"))
    elif _last_part_kind == "user-prompt":
        history.append(
            ModelResponse(parts=[TextPart(content=TRUNCATED_TURN_FILLER)], kind="response")
        )
