"""Reading back a turn from the chunks it left behind.

A turn writes what it produces to `ChatStreamChunk` as it goes (see
`AIAgentService`), in two kinds of row: text appended every fraction of a
second, and a snapshot of the whole turn appended rarely, carrying its
structure and the request the answer belongs to.

Rebuilding a turn is therefore always the same operation: take the last
snapshot, add the text that was appended after it. This module owns that, and
the three things callers want from it - is a turn still running, what does an
interrupted one look like, and fold it into the conversation for good.

Nothing here runs while a turn streams. It is all read-side, which is what
keeps the write path to "append a row".
"""

import logging

from django.db import transaction
from django.utils import timezone

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
)

from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ui_message_converter import model_message_to_ui_message
from chat.constants import STREAM_LIVE_WINDOW_SECONDS

logger = logging.getLogger(__name__)

# Every line tracing one turn goes to this logger rather than the module's, so
# following a cycle is one filter (`chat.turn`) across the four modules that
# take part in it, and its level can be raised or lowered on its own.
turn_logger = logging.getLogger("chat.turn")


def describe(conversation, chunks) -> None:
    """Log what a read makes of the chunks it found, when there are any.

    Silent on the usual read, where nothing is pending: this only speaks up
    for a conversation holding a turn that has not landed, which is the case
    worth being able to follow.
    """
    if not chunks:
        return
    turn_logger.info(
        "[read %s] %d pending chunk(s), turn is %s",
        conversation.pk,
        len(chunks),
        "still running" if is_live(chunks) else "over and interrupted",
    )


def is_live(chunks) -> bool:
    """True while chunks keep arriving, so a turn is still producing them.

    A turn that ends deletes its chunks, so rows only outlive it when it was
    cut short. Freshness is what tells "the answer is still coming" from "this
    is all there will be": the client that left mid-answer has to know which.
    """
    if not chunks:
        return False
    latest = max(chunk.created_at for chunk in chunks)
    return latest > timezone.now() - timezone.timedelta(seconds=STREAM_LIVE_WINDOW_SECONDS)


def fold(chunks) -> list[ModelMessage]:
    """The turn these chunks describe, in the shape a finished one has.

    The last snapshot is the turn as it was structurally, and everything after
    it is text the model produced since. Returns [] when the chunks hold
    nothing renderable yet.
    """
    ordered = sorted(chunks, key=lambda chunk: chunk.seq)
    snapshot = None
    trailing = []
    for chunk in ordered:
        if chunk.parts is not None:
            snapshot = chunk
            trailing = []
        elif chunk.text:
            trailing.append(chunk.text)

    if snapshot is None:
        # No snapshot means the turn was cut before its first one, so there is
        # no request to attach the text to and nothing worth storing.
        return []

    messages = ModelMessagesTypeAdapter.validate_python(snapshot.parts)
    text = "".join(trailing)
    if text:
        messages = _append_text(messages, text)
    return messages


def _append_text(messages: list[ModelMessage], text: str) -> list[ModelMessage]:
    """Add text the model produced after the snapshot was taken."""
    if messages and isinstance(messages[-1], ModelResponse):
        response = messages[-1]
        if response.parts and isinstance(response.parts[-1], TextPart):
            response.parts[-1].content += text
        else:
            response.parts.append(TextPart(content=text))
        return messages
    return list(messages) + [ModelResponse(parts=[TextPart(content=text)], kind="response")]


def interrupted_messages(chunks) -> list[UIMessage]:
    """The turn an interruption left behind, as the conversation shows it.

    Both sides of it: the question is in the snapshot too, since nothing was
    written before the model started answering. Built on read rather than on
    interruption, because by then the turn is in no position to write
    anything, which is the whole reason the chunks exist.
    """
    folded = fold(chunks)
    if not folded:
        return []

    ui_messages = []
    for message in folded:
        ui_message = model_message_to_ui_message(message)
        if ui_message is not None and ui_message.parts:
            ui_messages.append(ui_message)
    if not ui_messages:
        return []

    if ui_messages[-1].role != "assistant":
        # The question alone: the turn was cut before the model answered, which
        # is a long window when a document has to be parsed first. Showing it
        # is the point of writing it that early.
        return ui_messages

    answer = ui_messages[-1]
    # The question chunk is written before the answer has an id, so take the
    # first chunk that carries one.
    message_id = next((chunk.message_id for chunk in chunks if chunk.message_id), "")
    if message_id:
        answer.id = message_id
    answer.metadata = {**(answer.metadata or {}), "interrupted": True}
    return ui_messages


def persist(conversation) -> bool:
    """Fold the conversation's leftover chunks into it, for good.

    Called at the start of the next turn, so the model reads a history that
    holds the interrupted exchange rather than a question with no answer.
    Deliberately not called on read: a GET that writes is a GET that surprises
    someone, and the read path builds the same message without one.

    Returns True when there was something to fold.
    """
    chunks = list(conversation.stream_chunks.all())
    if not chunks:
        return False

    messages = fold(chunks)
    ui_messages = interrupted_messages(chunks)
    with transaction.atomic():
        if ui_messages:
            conversation.messages = list(conversation.messages) + ui_messages
            conversation.pydantic_messages = conversation.pydantic_messages + _dump(messages)
            conversation.save(update_fields=["messages", "pydantic_messages", "updated_at"])
        conversation.stream_chunks.all().delete()
    turn_logger.info(
        "[fold %s] %d chunk(s) became %d message(s)",
        conversation.pk,
        len(chunks),
        len(ui_messages),
    )
    return bool(ui_messages)


def _dump(messages: list[ModelMessage]) -> list:
    """The messages as `pydantic_messages` stores them."""
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")
