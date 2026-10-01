"""
Arena: blind champion-versus-challenger comparisons of LLM answers.

An arena turn streams two answers to the same user message, one from the
conversation's pinned production model (the champion) and one from a challenger
drawn from the active ``ArenaExperiment``. The user picks one; the pick is stored
on an ``ArenaComparison`` and the chosen answer is committed to the conversation.
Model names are never shown to the user. See ``docs/arena.md``.
"""

import logging
import random
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from core.feature_flags.helpers import is_feature_enabled

from chat import models
from chat.ai_sdk_types import FileUIPart, UIMessage
from chat.constants import IMAGE_MIME_PREFIX
from chat.enums import (
    ArenaComparisonStatus,
    ArenaRole,
    ArenaSide,
)
from chat.model_health import get_status_for_hrid
from chat.model_routing import resolve_effective_model_hrid
from chat.tools.self_documentation import anonymize_arena_documentation

logger = logging.getLogger(__name__)

# Arena draws are not security-sensitive; SystemRandom simply uses the OS entropy source.
_SYSTEM_RANDOM = random.SystemRandom()

# Tools whose execution leaves something behind outside the conversation (a generated
# file, a Docs edit). They are stripped from both models in arena mode so the losing
# answer never has side effects. ``generate_presentation`` is the only tool-based one
# today; edit-in-Docs is a separate endpoint, never reachable from a candidate stream.
SIDE_EFFECT_TOOL_NAMES = frozenset({"generate_presentation"})

RED = models.ModelHealth.Status.RED


class ArenaConflict(Exception):
    """Raised when a comparison is not in a state that accepts the requested action."""


def _refused_draws_key(experiment_id) -> str:
    return f"arena:refused_draws:{experiment_id}"


def get_refused_draws(experiment_id) -> int:
    """Number of draws refused because the conversation was not on the champion."""
    return int(cache.get(_refused_draws_key(experiment_id)) or 0)


def _count_refused_draw(experiment_id) -> None:
    key = _refused_draws_key(experiment_id)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=None)


def get_active_experiment() -> models.ArenaExperiment | None:
    """The single active experiment, with its challengers prefetched."""
    return (
        models.ArenaExperiment.objects.filter(is_active=True)
        .prefetch_related("challengers")
        .first()
    )


def message_has_image(message: UIMessage | None) -> bool:
    """Whether the user message carries at least one image attachment."""
    if message is None:
        return False
    return any(
        isinstance(part, FileUIPart) and (part.mediaType or "").startswith(IMAGE_MIME_PREFIX)
        for part in message.parts or []
    )


def message_has_document(message: UIMessage | None) -> bool:
    """Whether the user message carries a non-image attachment (parsed and indexed)."""
    if message is None:
        return False
    return any(
        isinstance(part, FileUIPart) and not (part.mediaType or "").startswith(IMAGE_MIME_PREFIX)
        for part in message.parts or []
    )


def _is_red(model_hrid: str) -> bool:
    return get_status_for_hrid(model_hrid) == RED


def _pin_conversation_model(
    conversation: models.ChatConversation, requested_model_hrid: str | None
) -> None:
    """Pin the conversation the same way ``post_conversation`` does on a first message.

    The model the user requested is honoured exactly as on a normal turn, so a draw
    never pins a model the turn would not have used. Compare-and-set on the empty
    ``model_hrid`` so a concurrent first message and a draw agree on the pinned model.
    """
    if conversation.model_hrid:
        return
    resolved = resolve_effective_model_hrid(requested_model_hrid)
    pinned = models.ChatConversation.objects.filter(pk=conversation.pk, model_hrid="").update(
        model_hrid=resolved
    )
    if pinned:
        conversation.model_hrid = resolved
    else:
        conversation.refresh_from_db(fields=["model_hrid"])


def _user_draws_today(experiment, user) -> int:
    since = timezone.now() - timedelta(days=1)
    return models.ArenaComparison.objects.filter(
        experiment=experiment, user=user, drawn_at__gte=since
    ).count()


def _conversation_has_image(conversation: models.ChatConversation) -> bool:
    """Whether an image is attached to the conversation (uploads land before the send)."""
    return conversation.attachments.filter(
        content_type__startswith=IMAGE_MIME_PREFIX,
        upload_state=models.AttachmentStatus.READY,
    ).exists()


def _eligible_challengers(
    experiment, conversation: models.ChatConversation, last_message: UIMessage | None
) -> list[str]:
    """Challengers that are healthy and, if the turn carries an image, can read images."""
    needs_image = message_has_image(last_message) or _conversation_has_image(conversation)
    eligible = []
    for challenger in experiment.challengers.all():
        configuration = settings.LLM_CONFIGURATIONS.get(challenger.model_hrid)
        if configuration is None or not configuration.is_active:
            continue
        if needs_image and not configuration.supports_image:
            continue
        if _is_red(challenger.model_hrid):
            continue
        eligible.append(challenger.model_hrid)
    return eligible


def _turn_index(conversation: models.ChatConversation) -> int:
    return sum(1 for message in conversation.messages if message.role == "user") + 1


@transaction.atomic
def draw_comparison(  # noqa: PLR0911, PLR0913  # pylint: disable=too-many-return-statements,too-many-arguments
    *,
    conversation: models.ChatConversation,
    user,
    force_web_search: bool,
    force_datagouv: bool = False,
    last_message: UIMessage | None = None,
    model_hrid: str | None = None,
) -> models.ArenaComparison | None:
    """Decide whether the next turn is an arena turn and, if so, create the comparison.

    Runs every eligibility rule of ``docs/arena.md``. Returns ``None`` when the turn is a
    normal one. A pending comparison left on the conversation is resolved first, so
    a reload or a quick second message never leaves two comparisons open.
    """
    if not is_feature_enabled(user, "arena"):
        return None
    experiment = get_active_experiment()
    if experiment is None:
        return None

    # All turn transitions lock the conversation before the comparison.
    conversation = models.ChatConversation.objects.select_for_update().get(pk=conversation.pk)
    resolve_pending(conversation)
    _pin_conversation_model(conversation, model_hrid)

    if conversation.model_hrid != experiment.champion_model_hrid:
        _count_refused_draw(experiment.pk)
        return None
    if _is_red(experiment.champion_model_hrid):
        return None
    # Both candidates would parse and index the same new document concurrently.
    if message_has_document(last_message):
        return None
    if _SYSTEM_RANDOM.random() >= experiment.sampling_rate:
        return None
    if _user_draws_today(experiment, user) >= experiment.daily_cap_per_user:
        return None

    challengers = _eligible_challengers(experiment, conversation, last_message)
    if not challengers:
        return None

    challenger_hrid = _SYSTEM_RANDOM.choice(challengers)
    champion_side = _SYSTEM_RANDOM.choice([ArenaSide.LEFT, ArenaSide.RIGHT])

    comparison = models.ArenaComparison.objects.create(
        experiment=experiment,
        conversation=conversation,
        user=user,
        turn=_turn_index(conversation),
        tools_stripped=is_feature_enabled(user, "presentation_generation"),
        champion_model_hrid=experiment.champion_model_hrid,
        challenger_model_hrid=challenger_hrid,
        champion_side=champion_side,
        conversation_version=conversation.arena_version,
        input_snapshot={
            "messages": [m.model_dump(mode="json") for m in conversation.messages],
            "pydantic_messages": conversation.pydantic_messages,
            "history_summary": conversation.history_summary,
            "history_summary_checkpoint": conversation.history_summary_checkpoint,
            "request_ui_message": last_message.model_dump(mode="json") if last_message else None,
            "force_web_search": force_web_search,
            "force_datagouv": force_datagouv,
        },
    )
    logger.info(
        "Arena draw on conversation %s: %s vs %s (champion on the %s)",
        conversation.pk,
        comparison.champion_model_hrid,
        comparison.challenger_model_hrid,
        champion_side,
    )
    return comparison


def get_pending_comparison(conversation) -> models.ArenaComparison | None:
    """The pending comparison of a conversation, if any."""
    return models.ArenaComparison.objects.filter(
        conversation=conversation, status=ArenaComparisonStatus.PENDING
    ).first()


@contextmanager
def locked_comparison(comparison):
    """Serialize commits, cancellation, votes and deletion in a fixed lock order."""
    with transaction.atomic():
        conversation = (
            models.ChatConversation.objects.select_for_update()
            .filter(pk=comparison.conversation_id)
            .first()
        )
        current = models.ArenaComparison.objects.select_for_update().get(pk=comparison.pk)
        current.conversation = conversation if current.conversation_id else None
        yield current


def _version_matches(comparison) -> bool:
    return (
        comparison.conversation is not None
        and comparison.conversation.arena_version == comparison.conversation_version
    )


def _late_message_is_eligible(comparison, message: UIMessage | None) -> bool:
    """Whether a message first seen at claim time passes the draw's attachment rules."""
    if message_has_document(message):
        return False
    if not message_has_image(message):
        return True
    configuration = settings.LLM_CONFIGURATIONS.get(comparison.challenger_model_hrid)
    return configuration is not None and configuration.supports_image


def claim_candidate(comparison, role, message):
    """Only one request may start each candidate; both consume the same input."""
    with locked_comparison(comparison) as current:
        if current.status != ArenaComparisonStatus.PENDING or not _version_matches(current):
            raise ArenaConflict("arena_comparison_closed")
        if getattr(current, f"{role}_started_at") or current.side_finished(role):
            raise ArenaConflict("arena_side_already_started")
        snapshot = current.input_snapshot
        if snapshot is None:
            # Comparisons predating input snapshots cannot safely be resumed.
            raise ArenaConflict("arena_comparison_has_no_snapshot")
        if snapshot["request_ui_message"] is None:
            # The draw did not see this message: apply its attachment rules now.
            if not _late_message_is_eligible(current, message):
                raise ArenaConflict("arena_message_not_eligible")
            snapshot["request_ui_message"] = message.model_dump(mode="json")
        setattr(current, f"{role}_started_at", timezone.now())
        current.save(update_fields=[f"{role}_started_at", "input_snapshot", "updated_at"])
        return current


def snapshot_conversation(conversation, comparison):
    """Build an in-memory conversation for inference without reading mutable history."""
    snapshot = comparison.input_snapshot
    conversation = deepcopy(conversation)
    conversation.messages = [UIMessage.model_validate(m) for m in snapshot["messages"]]
    conversation.pydantic_messages = deepcopy(snapshot["pydantic_messages"])
    conversation.history_summary = snapshot["history_summary"]
    conversation.history_summary_checkpoint = snapshot["history_summary_checkpoint"]
    return conversation


def build_turn_payload(
    *,
    request_ui_message: UIMessage | None,
    output_ui_message: UIMessage,
    pydantic_messages: list,
    usage: dict,
) -> dict:
    """Serialize one candidate answer so it can be committed to the conversation later."""
    return {
        "request_ui_message": (
            request_ui_message.model_dump(mode="json") if request_ui_message else None
        ),
        "output_ui_message": anonymize_arena_documentation(
            output_ui_message.model_dump(mode="json")
        ),
        "pydantic_messages": anonymize_arena_documentation(pydantic_messages),
        "usage": {
            "promptTokens": int(usage.get("promptTokens", 0) or 0),
            "completionTokens": int(usage.get("completionTokens", 0) or 0),
            "co2_impact": float(usage.get("co2_impact", 0) or 0),
        },
    }


def _request_id(comparison: models.ArenaComparison) -> str | None:
    """Id of the user message this comparison answers, as the client sent it."""
    return ((comparison.input_snapshot or {}).get("request_ui_message") or {}).get("id")


def _ends_with_request(conversation: models.ChatConversation, request_id: str | None) -> bool:
    """Whether the stored history already ends with this turn's user message.

    Compared by id: a question left unanswered by an earlier turn (stopped before
    any answer) also ends the history with a user message, but it is not this one.
    """
    messages = conversation.messages
    return bool(
        request_id and messages and messages[-1].role == "user" and messages[-1].id == request_id
    )


def commit_payload(
    conversation: models.ChatConversation, payload: dict, request_id: str | None = None
) -> None:
    """Append a candidate answer to the conversation exactly as a normal turn would.

    Mirrors ``AIAgentService._prepare_update_conversation``: the user bubble is only
    rebuilt when the stored history does not already end with this turn's user
    message (``request_id``), the assistant bubble is appended, the pydantic history
    is extended and usage totals accumulate.
    """
    new_messages = list(conversation.messages)
    if payload.get("request_ui_message") and not _ends_with_request(conversation, request_id):
        new_messages.append(UIMessage.model_validate(payload["request_ui_message"]))
    new_messages.append(UIMessage.model_validate(payload["output_ui_message"]))
    conversation.messages = new_messages
    conversation.pydantic_messages = list(conversation.pydantic_messages) + list(
        payload.get("pydantic_messages", [])
    )
    usage = dict(conversation.agent_usage or {})
    for key in ("promptTokens", "completionTokens", "co2_impact"):
        usage[key] = usage.get(key, 0) + payload["usage"].get(key, 0)
    conversation.agent_usage = usage
    conversation.save(update_fields=["messages", "pydantic_messages", "agent_usage", "updated_at"])


def record_side_result(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    comparison: models.ArenaComparison,
    role: str,
    *,
    payload: dict | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    co2_impact: float | None = None,
    latency_ms: int | None = None,
    first_token_ms: int | None = None,
    trace_id: str = "",
    error: str = "",
) -> None:
    """Commit a result at most once, while its comparison and turn are current."""
    with locked_comparison(comparison) as current:
        if (
            current.status != ArenaComparisonStatus.PENDING
            or not _version_matches(current)
            or current.side_finished(role)
        ):
            return
        _store_side_result(
            current,
            role,
            payload=payload,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            co2_impact=co2_impact,
            latency_ms=latency_ms,
            first_token_ms=first_token_ms,
            trace_id=trace_id,
            error=error,
        )
    comparison.refresh_from_db()


def _store_side_result(comparison, role, **values):
    """Persist under the conversation and comparison locks held by the caller."""
    payload = values["payload"]
    error = values["error"]
    values["finished_at"] = timezone.now()
    update_fields = []
    for name, value in values.items():
        field = f"{role}_{name}"
        setattr(comparison, field, value)
        update_fields.append(field)
    # The production answer goes into the history right away: whatever the user
    # does next (votes, leaves, reloads, closes the tab), the conversation is never
    # left without an answer. A vote for the challenger swaps it (see ``vote``).
    if (
        role == ArenaRole.CHAMPION
        and payload is not None
        and not error
        and comparison.conversation is not None
        and not comparison.champion_committed
    ):
        commit_payload(comparison.conversation, payload, _request_id(comparison))
        comparison.champion_committed = True
        update_fields.append("champion_committed")
    comparison.save(update_fields=update_fields + ["updated_at"])


def replace_last_turn(conversation: models.ChatConversation, old: dict, new: dict) -> None:
    """Swap the assistant answer of the last turn: ``old`` was committed, ``new`` replaces it.

    Used when the user prefers the challenger after the champion answer was
    already written to the history. The user bubble stays, the assistant bubble,
    the pydantic history of that turn and the usage totals are exchanged.
    """
    messages = list(conversation.messages)
    if messages and messages[-1].role == "assistant":
        messages[-1] = UIMessage.model_validate(new["output_ui_message"])
    else:
        messages.append(UIMessage.model_validate(new["output_ui_message"]))
    conversation.messages = messages

    history = list(conversation.pydantic_messages)
    old_len = len(old.get("pydantic_messages", []))
    if old_len:
        history = history[: len(history) - old_len]
    conversation.pydantic_messages = history + list(new.get("pydantic_messages", []))

    usage = dict(conversation.agent_usage or {})
    for key in ("promptTokens", "completionTokens", "co2_impact"):
        usage[key] = usage.get(key, 0) - old["usage"].get(key, 0) + new["usage"].get(key, 0)
    conversation.agent_usage = usage
    conversation.save(update_fields=["messages", "pydantic_messages", "agent_usage", "updated_at"])


def _ensure_champion_committed(comparison: models.ArenaComparison) -> None:
    """Write the champion answer if ``record_side_result`` could not (no conversation then)."""
    if comparison.champion_committed or not _version_matches(comparison):
        return
    if comparison.side_succeeded(ArenaRole.CHAMPION):
        commit_payload(
            comparison.conversation, comparison.champion_payload, _request_id(comparison)
        )
        comparison.champion_committed = True


def _keep_user_message(comparison: models.ArenaComparison) -> None:
    """Store the user message of a turn that ends without the champion's answer.

    A normal turn does the same when the model fails, so the question stays in the
    history and can be asked again. The guard on the last message id keeps it
    idempotent without dropping a new question after an earlier unanswered one.
    """
    conversation = comparison.conversation
    request = (comparison.input_snapshot or {}).get("request_ui_message")
    if conversation is None or request is None:
        return
    if _ends_with_request(conversation, request.get("id")):
        return
    conversation.messages = [*conversation.messages, UIMessage.model_validate(request)]
    conversation.save(update_fields=["messages", "updated_at"])


def _close_without_vote(comparison: models.ArenaComparison, reason: str | None = None) -> None:
    """Keep the champion answer if it exists and close the comparison."""
    conversation = comparison.conversation
    failed = bool(comparison.champion_error or comparison.challenger_error)
    comparison.closed_reason = "candidate_failed" if failed else "user_abandoned"
    if not _version_matches(comparison):
        comparison.status = ArenaComparisonStatus.ERRORED
        comparison.closed_reason = "superseded"
    elif comparison.side_succeeded(ArenaRole.CHAMPION) and conversation is not None:
        _ensure_champion_committed(comparison)
        comparison.status = (
            ArenaComparisonStatus.ERRORED if failed else ArenaComparisonStatus.ABANDONED
        )
    else:
        comparison.status = ArenaComparisonStatus.ERRORED
        _keep_user_message(comparison)
        if not comparison.champion_error and not comparison.side_finished(ArenaRole.CHAMPION):
            comparison.champion_error = "unfinished when the comparison was resolved"
            if not failed:
                comparison.closed_reason = "cancelled"
    if reason == "cancelled":
        comparison.status = ArenaComparisonStatus.ERRORED
        comparison.closed_reason = reason
    comparison.save(
        update_fields=[
            "status",
            "closed_reason",
            "champion_error",
            "champion_committed",
            "updated_at",
        ]
    )


def resolve_pending(
    conversation: models.ChatConversation, *, reason: str | None = None
) -> models.ArenaComparison | None:
    """Close a comparison the user walked away from, keeping the champion's answer.

    Called before any new turn or draw on the conversation, and by the vote
    endpoint when the client abandons explicitly. Returns the resolved comparison.
    """
    with transaction.atomic():
        current_conversation = models.ChatConversation.objects.select_for_update().get(
            pk=conversation.pk
        )
        pending = (
            models.ArenaComparison.objects.select_for_update()
            .filter(conversation=conversation, status=ArenaComparisonStatus.PENDING)
            .first()
        )
        if pending is not None:
            pending.conversation = current_conversation
            _close_without_vote(pending, reason=reason)
        current_conversation.arena_version += 1
        current_conversation.save(update_fields=["arena_version"])
        conversation.refresh_from_db()
        return pending


def vote(comparison: models.ArenaComparison, side: str | None) -> models.ArenaComparison:
    """Record the user's pick and commit the chosen answer.

    ``side`` is the displayed column, never a model name. ``None`` abandons the
    comparison and keeps the champion answer. Raises ``ArenaConflict`` when the
    comparison is not pending or a side has not finished streaming.
    """
    with locked_comparison(comparison) as current:
        comparison = current
        if comparison.status != ArenaComparisonStatus.PENDING:
            raise ArenaConflict("This comparison is already closed.")
        if side is None:
            _close_without_vote(comparison)
            return comparison
        if not _version_matches(comparison):
            raise ArenaConflict("The conversation has moved to another turn.")
        if not (
            comparison.side_finished(ArenaRole.CHAMPION)
            and comparison.side_finished(ArenaRole.CHALLENGER)
        ):
            raise ArenaConflict("Both answers must be finished before voting.")

        role = comparison.role_for_side(side)
        if not comparison.side_succeeded(role):
            # The chosen side failed: nothing to keep from it, fall back to the champion.
            _close_without_vote(comparison)
            return comparison

        other = ArenaRole.CHALLENGER if role == ArenaRole.CHAMPION else ArenaRole.CHAMPION
        if role == ArenaRole.CHAMPION:
            _ensure_champion_committed(comparison)
        elif comparison.champion_committed:
            replace_last_turn(
                comparison.conversation, comparison.champion_payload, comparison.challenger_payload
            )
        else:
            commit_payload(
                comparison.conversation, comparison.challenger_payload, _request_id(comparison)
            )
        now = timezone.now()
        finished = [
            getattr(comparison, f"{r}_finished_at")
            for r in (ArenaRole.CHAMPION, ArenaRole.CHALLENGER)
            if getattr(comparison, f"{r}_finished_at")
        ]
        comparison.time_to_vote_ms = int((now - max(finished)).total_seconds() * 1000)
        comparison.voted_at = now
        if comparison.side_succeeded(other):
            comparison.status = ArenaComparisonStatus.VOTED
            comparison.winner = role
        else:
            # One answer never arrived: the user did not really compare anything.
            comparison.status = ArenaComparisonStatus.ERRORED
            comparison.closed_reason = "candidate_failed"
        comparison.save(
            update_fields=[
                "status",
                "closed_reason",
                "winner",
                "voted_at",
                "time_to_vote_ms",
                "champion_committed",
                "updated_at",
            ]
        )
        return comparison


MILESTONES = {1: "first_vote", 10: "tenth_vote", 100: "hundredth_vote"}


def build_acknowledgement(comparison: models.ArenaComparison, user) -> dict | None:
    """The thank-you block returned by the vote endpoint, ``None`` unless it was a vote.

    ``user_votes`` spans all experiments: the 90-day redaction nulls ``user`` on old
    comparisons, so the count is naturally "recent".
    """
    if comparison.status != ArenaComparisonStatus.VOTED or user is None:
        return None
    voted = models.ArenaComparison.objects.filter(status=ArenaComparisonStatus.VOTED)
    user_votes = voted.filter(user=user).count()
    return {
        "user_votes": user_votes,
        "experiment_votes": voted.filter(experiment_id=comparison.experiment_id).count(),
        "milestone": MILESTONES.get(user_votes),
    }
