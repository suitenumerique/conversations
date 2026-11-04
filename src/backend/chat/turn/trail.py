"""The rows a turn leaves behind while it runs, so a cut-short turn is not lost.

A turn appends its question, its text and its structure to `ChatStreamChunk`
rows as it goes. When it lands, the rows are dropped in the same transaction
that stores the turn; when it does not, `chat.stream_chunks` folds them back
into the conversation.
"""

import copy
import itertools
import json
import logging
import time
import uuid
from typing import Callable, List, Optional

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from asgiref.sync import sync_to_async
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)

from chat import models
from chat.clients.schema import ImagePostRunActions
from chat.constants import STREAM_TEXT_FLUSH_CHARS, STREAM_TEXT_FLUSH_INTERVAL_SECONDS
from chat.stream_chunks import close as close_turn_trail
from chat.turn.persistence import apply_image_actions

# Same logger as the turn's own log lines, so one cycle reads top to bottom.
turn_logger = logging.getLogger("chat.turn")


class TurnTrail:  # pylint: disable=too-many-instance-attributes
    """The chunk rows of one turn, and the state needed to write them.

    One per turn: a new one starts with a new `run_id`, which scopes this turn's
    rows so a turn running at the same time on the same conversation cannot
    fold, overwrite or delete them.

    The service sets the attributes it owns the timing of: `message_id` once the
    stream has one, `image_actions` once the prompt is prepared,
    `question_stored` when the image-skip path stores the question, `landed`
    when the turn is filed, and `active_stream` while a model node streams.
    """

    def __init__(self, conversation: models.ChatConversation, log: Callable[..., None]):
        self.conversation = conversation
        self._log = log
        self.run_id = uuid.uuid4()
        self.message_id: str | None = None
        self.image_actions: Optional[ImagePostRunActions] = None
        self.question_stored = False
        self.landed = False
        # The stream of the model node running now: it carries the response
        # Pydantic AI is building, which a snapshot stores for the part of the
        # turn not yet closed.
        self.active_stream = None
        self.text_rows = 0
        self.snapshot_rows = 0
        # Where we are in the sequence, the text produced since the last row,
        # and when text was last written.
        self._chunk_seq = itertools.count()
        self._pending_text = ""
        self._last_text_flush = 0
        self._tool_step_pending = False

    async def beat(self) -> None:
        """Prove the turn is still running, when it has nothing to show for it.

        A turn blocked on a document parse, a summary or a long tool call
        produces no rows for minutes, and a trail that stops growing is read as
        one an interruption left behind. So the keepalive loop - the only thing
        that ticks while the stream is silent - appends a row that says nothing
        except when it was written.

        `fold` ignores a row with no text and no parts, and `is_live` already
        reads the newest row's timestamp, so this needs nothing from either.

        The check and the insert are not one step, so the turn can land in
        between and take its trail with it. Rechecking afterwards and removing
        the row is what keeps a landed turn from looking like it is still
        generating for the length of the liveness window.
        """
        if self.landed:
            return
        seq = await self._write_chunk()
        # Not always false, whatever static analysis makes of it: the turn sets this
        # itself, from its own task or thread, while the insert above is in flight.
        if self.landed:  # NOSONAR
            await self._beat_rows(seq).adelete()

    def beat_sync(self) -> None:
        """`beat`, for the WSGI path, where the keepalive loop is not async."""
        if self.landed:
            return
        seq = next(self._chunk_seq)
        models.ChatStreamChunk.objects.create(
            conversation=self.conversation,
            run_id=self.run_id,
            message_id=self.message_id or "",
            seq=seq,
        )
        turn_logger.info("chunk %d: still running", seq)
        if self.landed:  # NOSONAR
            # Landed while this row was being written; see `beat`.
            self._beat_rows(seq).delete()

    def _beat_rows(self, seq: int):
        """The one row a beat just wrote, so it can take it back."""
        return models.ChatStreamChunk.objects.filter(
            conversation=self.conversation, run_id=self.run_id, seq=seq
        )

    def _rows_before(self, seq: int):
        """This turn's rows that a snapshot at `seq` has made unreadable."""
        return models.ChatStreamChunk.objects.filter(
            conversation=self.conversation, run_id=self.run_id, seq__lt=seq
        )

    async def append_text(self, text: str) -> None:
        """Append text the model has produced, batched.

        The batching is the whole cost control: a row every quarter second
        rather than one per token, and each row carries only what is new. A
        turn cut short loses at most the batch in hand, and only when nothing
        got the chance to file it: every path that files its own trail flushes
        first, in `file`.
        """
        self._pending_text += text
        now = time.monotonic()
        if (
            now - self._last_text_flush < STREAM_TEXT_FLUSH_INTERVAL_SECONDS
            and len(self._pending_text) < STREAM_TEXT_FLUSH_CHARS
        ):
            return
        await self._flush_text()

    async def file(self) -> None:
        """Write the text in hand, then file the trail as one exchange.

        The flush comes first because a whole batch of text - up to 200
        characters, or a quarter second of it - is still in hand when a turn
        ends this way, and filing without it drops the end of the sentence the
        reader was already shown.

        One coroutine rather than two awaits at the call site: the cancelled
        path shields this, and a shield covers one awaitable, so the flush and
        the fold have to be inside the same one to be ordered at all once the
        task around them is being torn down.

        Skipped when the conversation was deleted while the turn ran: there is
        nothing left to file into, and writing a chunk for it would fail. The
        check runs again when the write fails, since the delete can land
        between the first check and the write: the chunk's own validation then
        rejects the gone conversation, the insert does if the delete lands
        later still, and the filing's locked re-read finds no row if it lands
        after the flush. Any of these is raised while the conversation exists.
        """
        if not await self._conversation_exists():
            self._log("conversation deleted, nothing to file")
            return
        try:
            await self._flush_text()
            await sync_to_async(close_turn_trail)(self.conversation, self.run_id)
        except ValidationError, IntegrityError, models.ChatConversation.DoesNotExist:
            if await self._conversation_exists():
                raise
            self._log("conversation deleted while filing, nothing to file")

    def drop_rows(self) -> None:
        """Mark the turn landed and delete its rows, inside the transaction storing it."""
        # Before the delete, so a beat that reads it from here on returns
        # without writing. One already past that check can still insert
        # after the delete, which is why `beat` rechecks and removes its
        # own row.
        self.landed = True
        # This turn's trail only: another turn may be streaming into the
        # same conversation from another tab, and its rows are not ours.
        self.conversation.stream_chunks.filter(run_id=self.run_id).delete()

    async def _conversation_exists(self) -> bool:
        """Whether the conversation is still in the database."""
        return await models.ChatConversation.objects.filter(pk=self.conversation.pk).aexists()

    async def _flush_text(self) -> None:
        """Write the text in hand, if any."""
        if not self._pending_text:
            return
        text, self._pending_text = self._pending_text, ""
        self._last_text_flush = time.monotonic()
        await self._write_chunk(text=text)

    async def append_snapshot(self, run) -> None:
        """Append the turn as it stands, structure and all.

        Text rows say what the model wrote; only this says what it was doing.
        Written when the turn's structure changes and at no other time, since
        it is the expensive kind of row: the question, and a tool step once its
        returns are in the run.
        """
        # Everything in hand is in the response the snapshot is about to store,
        # so it is superseded rather than written first.
        self._pending_text = ""
        await self._write_snapshot(self._partial_turn_messages(run))

    def note_tool_step(self) -> None:
        """A tool step has been streamed: it owes a snapshot once its returns are in."""
        self._tool_step_pending = True

    async def snapshot_closed_tool_step(self, run) -> None:
        """Snapshot the tool cycle that just closed, if one is waiting for it."""
        if self._tool_step_pending:
            self._tool_step_pending = False
            await self.append_snapshot(run)

    async def append_question(self, user_prompt: str, input_images: List) -> None:
        """Append the question, before anything slow gets the chance to run.

        Everything between the request arriving and the model's first token -
        preparing the run, re-indexing, parsing an attached document, waiting
        on a summary - happens before there is any output to snapshot. Leaving
        it at that would mean a turn cut short in that window stored nothing at
        all, not even what was asked, and parsing a document alone can hold it
        open for minutes.
        """
        await self._write_snapshot(
            [
                ModelRequest(
                    parts=[UserPromptPart(content=[user_prompt] + list(input_images))],
                    kind="request",
                )
            ]
        )

    async def _write_snapshot(self, messages: List[ModelMessage]) -> None:
        """Store `messages` as a snapshot chunk, and drop what it supersedes.

        Copied and rewritten before it is stored: image URLs presigned for the
        model expire, so what goes on disk carries the durable form. Doing that
        to the run's own messages would change what the model sees for the rest
        of the turn.

        Every row before a snapshot is already inside it, because `fold` throws
        away the text it has collected each time it meets one. Keeping them
        costs a trail that grows with the square of the steps - each snapshot
        holds the whole turn so far - for rows no reader can ever reach.

        The delete comes after the insert, never before: the worst a failure
        between the two can do is leave the rows that would have been left
        anyway, whereas the other order can leave a trail with no snapshot in
        it at all.

        `question_in_messages` rides along on every snapshot, not just the
        question's own. The image-skip path has already put the question in
        `messages`, markers and all; the snapshot still carries the request,
        because the history needs it, but a reader must not show it twice, and
        the row that said so may be one of the rows being dropped here.
        """
        if not messages:
            return
        messages = copy.deepcopy(messages)
        apply_image_actions(messages, self.image_actions)
        seq = await self._write_chunk(
            parts=json.loads(ModelMessagesTypeAdapter.dump_json(messages).decode("utf-8")),
            question_in_messages=self.question_stored,
        )
        superseded, _ = await self._rows_before(seq).adelete()
        if superseded:
            self._log("chunk %d superseded %d row(s)", seq, superseded)

    async def _write_chunk(
        self, *, text: str = "", parts=None, question_in_messages: bool = False
    ) -> int:
        """Append one row to the turn's chunks.

        Two writers share this trail: the turn, and the keepalive beating for
        it while it is blocked. Under ASGI they are two tasks, under WSGI two
        threads, so `seq = n; n += 1` is read twice either way and collides on
        the constraint. `next()` on an `itertools.count` is one atomic step in
        both.
        """
        seq = next(self._chunk_seq)
        await models.ChatStreamChunk.objects.acreate(
            conversation=self.conversation,
            run_id=self.run_id,
            message_id=self.message_id or "",
            seq=seq,
            text=text,
            parts=parts,
            question_in_messages=question_in_messages,
        )
        if parts is None and not text:
            turn_logger.info("chunk %d: still running", seq)
        elif parts is None:
            self.text_rows += 1
            turn_logger.debug(
                "[turn %s] chunk %d: %d characters of text",
                self.conversation.pk,
                seq,
                len(text),
            )
        else:
            self.snapshot_rows += 1
            self._log("chunk %d: snapshot of %d message(s)", seq, len(parts))
        return seq

    def _partial_turn_messages(self, run) -> List[ModelMessage]:
        """The turn as it stands right now.

        `run.new_messages()` holds the steps already closed. The response still
        being streamed is not among them, but Pydantic AI builds it as it goes
        and hands it over on `AgentStream.response`.
        """
        messages = list(run.new_messages())
        stream = self.active_stream
        if stream is not None:
            response = stream.response
            if response.parts and not any(message is response for message in messages):
                messages.append(response)
        return messages
