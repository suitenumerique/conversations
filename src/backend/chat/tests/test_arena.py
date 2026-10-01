"""Unit tests for the arena service: eligibility, commit, vote and results math."""

# pylint: disable=redefined-outer-name, unused-argument, protected-access

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections
from django.utils import timezone

import pytest

from core.factories import UserFactory
from core.feature_flags.flags import FeatureFlags, FeatureToggle

from chat import arena
from chat.ai_sdk_types import FileUIPart, TextUIPart, UIMessage
from chat.arena_results import _rate_block, build_results, wilson_interval
from chat.clients.pydantic_ai import AIAgentService
from chat.enums import (
    ArenaComparisonStatus,
    ArenaRole,
    ArenaSide,
)
from chat.factories import (
    ArenaChallengerFactory,
    ArenaComparisonFactory,
    ArenaExperimentFactory,
    ChatConversationAttachmentFactory,
    ChatConversationFactory,
)
from chat.llm_configuration import LLModel, LLMProvider
from chat.model_health import model_health_cache_key
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def _make_llm(hrid: str, supports_image: bool = False, tools=None) -> LLModel:
    return LLModel(
        hrid=hrid,
        model_name=f"{hrid}-llm",
        human_readable_name=hrid,
        is_active=True,
        supports_image=supports_image,
        system_prompt="You are a helpful assistant.",
        tools=tools or [],
        provider=LLMProvider(
            hrid="albert", base_url="https://www.external-ai-service.com/", api_key="k"
        ),
    )


@pytest.fixture(autouse=True)
def arena_settings(settings):
    """Two configured models, the arena flag on, a clean cache."""
    settings.LLM_CONFIGURATIONS = {
        "main-model": _make_llm("main-model"),
        "challenger-model": _make_llm("challenger-model"),
        "vision-challenger": _make_llm("vision-challenger", supports_image=True),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "main-model"
    settings.LLM_FALLBACK_MODEL_HRID_1 = ""
    settings.LLM_FALLBACK_MODEL_HRID_2 = ""
    settings.FEATURE_FLAGS = FeatureFlags(
        web_search=FeatureToggle.ENABLED,
        document_upload=FeatureToggle.ENABLED,
        presentation_generation=FeatureToggle.DISABLED,
        arena=FeatureToggle.ENABLED,
    )
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def experiment():
    """An active experiment with one challenger."""
    experiment = ArenaExperimentFactory(is_active=True, champion_model_hrid="main-model")
    ArenaChallengerFactory(experiment=experiment, model_hrid="challenger-model")
    return experiment


def _payload(text: str, prompt_tokens=10, completion_tokens=20) -> dict:
    return arena.build_turn_payload(
        request_ui_message=UIMessage(
            id="u1", role="user", content="Hello", parts=[TextUIPart(type="text", text="Hello")]
        ),
        output_ui_message=UIMessage(
            id="a1", role="assistant", content=text, parts=[TextUIPart(type="text", text=text)]
        ),
        pydantic_messages=[{"kind": "request"}, {"kind": "response", "text": text}],
        usage={
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "co2_impact": 0.5,
        },
    )


# --------------------------------------------------------------------------- #
# Draw and eligibility
# --------------------------------------------------------------------------- #


def test_draw_creates_pending_comparison_pinned_to_champion(experiment):
    """An eligible turn yields a pending comparison and pins the conversation to the champion."""
    conversation = ChatConversationFactory()

    comparison = arena.draw_comparison(
        conversation=conversation, user=conversation.owner, force_web_search=False
    )

    assert comparison is not None
    assert comparison.status == ArenaComparisonStatus.PENDING
    assert comparison.champion_model_hrid == "main-model"
    assert comparison.challenger_model_hrid == "challenger-model"
    assert comparison.champion_side in (ArenaSide.LEFT, ArenaSide.RIGHT)
    assert comparison.turn == 1
    conversation.refresh_from_db()
    assert conversation.model_hrid == "main-model"


def test_draw_refused_when_flag_disabled(settings, experiment):
    """The feature flag off means no arena, whatever the experiment says."""
    settings.FEATURE_FLAGS = FeatureFlags(arena=FeatureToggle.DISABLED)
    conversation = ChatConversationFactory()

    assert (
        arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )
        is None
    )


def test_draw_refused_without_active_experiment():
    """An inactive experiment never draws."""
    inactive = ArenaExperimentFactory(is_active=False)
    ArenaChallengerFactory(experiment=inactive)
    conversation = ChatConversationFactory()

    assert (
        arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )
        is None
    )


def test_draw_respects_sampling_rate(experiment):
    """A zero sampling rate never draws, a full one always does."""
    experiment.sampling_rate = 0.0
    experiment.save()
    conversation = ChatConversationFactory()
    assert (
        arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )
        is None
    )

    experiment.sampling_rate = 1.0
    experiment.save()
    assert (
        arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )
        is not None
    )


def test_draw_respects_daily_cap(experiment):
    """Once the user reached the daily cap, no more arena turns today."""
    experiment.daily_cap_per_user = 1
    experiment.save()
    user = UserFactory()
    first = ChatConversationFactory(owner=user)
    second = ChatConversationFactory(owner=user)

    drawn = arena.draw_comparison(conversation=first, user=user, force_web_search=False)
    assert drawn is not None
    # The first comparison is resolved (abandoned) by the second draw attempt, but the
    # cap still counts it.
    assert arena.draw_comparison(conversation=second, user=user, force_web_search=False) is None


def test_draw_refused_when_conversation_not_on_champion(experiment):
    """A conversation pinned to another model is never compared, and the refusal is counted."""
    conversation = ChatConversationFactory(model_hrid="challenger-model")

    assert (
        arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )
        is None
    )
    assert arena.get_refused_draws(experiment.pk) == 1


def test_draw_skips_red_challenger(experiment):
    """A challenger reported red by the health poller is not drawn."""
    cache.set(model_health_cache_key("albert", "challenger-model-llm"), "red", timeout=None)
    conversation = ChatConversationFactory()

    assert (
        arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )
        is None
    )


def test_draw_skips_text_only_challenger_when_image_attached(experiment):
    """With an image on the turn, only image-capable challengers are eligible."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        content_type="image/png",
        file_name="cat.png",
        upload_state="ready",
    )

    assert (
        arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )
        is None
    )

    ArenaChallengerFactory(experiment=experiment, model_hrid="vision-challenger")
    comparison = arena.draw_comparison(
        conversation=conversation, user=conversation.owner, force_web_search=False
    )
    assert comparison is not None
    assert comparison.challenger_model_hrid == "vision-challenger"


def test_draw_pins_an_unpinned_conversation_to_the_requested_model(experiment):
    """The draw honours the selected model like a normal first turn, then refuses."""
    conversation = ChatConversationFactory()

    assert (
        arena.draw_comparison(
            conversation=conversation,
            user=conversation.owner,
            force_web_search=False,
            model_hrid="challenger-model",
        )
        is None
    )
    conversation.refresh_from_db()
    assert conversation.model_hrid == "challenger-model"


def test_draw_skipped_when_the_message_carries_a_document(experiment):
    """Both candidates would parse and index the same new document: no arena turn."""
    conversation = ChatConversationFactory()
    message = UIMessage(
        id="u1",
        role="user",
        content="Read this",
        parts=[
            TextUIPart(type="text", text="Read this"),
            FileUIPart(
                type="file", mediaType="application/pdf", url="/media/doc.pdf", filename="d.pdf"
            ),
        ],
    )

    assert (
        arena.draw_comparison(
            conversation=conversation,
            user=conversation.owner,
            force_web_search=False,
            last_message=message,
        )
        is None
    )


# --------------------------------------------------------------------------- #
# Recording, committing, voting, resolving
# --------------------------------------------------------------------------- #


def test_recording_the_champion_commits_its_answer_immediately():
    """The production answer lands in the history as soon as it is ready.

    Whatever the user does next (vote, leave, reload), the conversation is never
    left without an answer.
    """
    comparison = ArenaComparisonFactory()

    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))

    comparison.refresh_from_db()
    assert comparison.champion_committed is True
    comparison.conversation.refresh_from_db()
    assert [m.content for m in comparison.conversation.messages] == ["Hello", "A"]

    # Recording the challenger never touches the history.
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, payload=_payload("B"))
    comparison.conversation.refresh_from_db()
    assert [m.content for m in comparison.conversation.messages] == ["Hello", "A"]


def test_record_side_result_stores_metrics():
    """Recording a side fills its flat columns."""
    comparison = ArenaComparisonFactory()

    arena.record_side_result(
        comparison,
        ArenaRole.CHALLENGER,
        payload=_payload("B"),
        prompt_tokens=11,
        completion_tokens=22,
        co2_impact=0.1,
        latency_ms=1200,
        first_token_ms=300,
        trace_id="abc",
    )

    comparison.refresh_from_db()
    assert comparison.challenger_prompt_tokens == 11
    assert comparison.challenger_completion_tokens == 22
    assert comparison.challenger_latency_ms == 1200
    assert comparison.challenger_first_token_ms == 300
    assert comparison.challenger_trace_id == "abc"
    assert comparison.challenger_finished_at is not None
    assert comparison.side_succeeded(ArenaRole.CHALLENGER)


def test_commit_payload_appends_turn_like_a_normal_run():
    """Committing appends user and assistant bubbles, history and usage totals."""
    conversation = ChatConversationFactory(agent_usage={"promptTokens": 5})

    arena.commit_payload(conversation, _payload("Hello there"))

    conversation.refresh_from_db()
    assert [m.role for m in conversation.messages] == ["user", "assistant"]
    assert conversation.messages[1].content == "Hello there"
    assert len(conversation.pydantic_messages) == 2
    assert conversation.agent_usage == {
        "promptTokens": 15,
        "completionTokens": 20,
        "co2_impact": 0.5,
    }


def test_commit_payload_skips_user_bubble_when_already_stored():
    """A user bubble already persisted (error path) is not duplicated on commit."""
    conversation = ChatConversationFactory(
        messages=[
            UIMessage(
                id="u0", role="user", content="Hello", parts=[TextUIPart(type="text", text="Hello")]
            )
        ]
    )

    arena.commit_payload(conversation, _payload("Hi"), request_id="u0")

    conversation.refresh_from_db()
    assert [m.role for m in conversation.messages] == ["user", "assistant"]


def test_unanswered_earlier_question_does_not_swallow_the_next_one():
    """A question left without an answer (Stop before any text) is not this turn's.

    The next arena turn still stores its own question, whether its answer is
    committed or it also ends without one, so no answer lands under the wrong question.
    """
    dangling = UIMessage(
        id="u0", role="user", content="First", parts=[TextUIPart(type="text", text="First")]
    )
    question = _payload("unused")["request_ui_message"]

    answered = ArenaComparisonFactory(
        conversation=ChatConversationFactory(messages=[dangling]),
        input_snapshot={"request_ui_message": question},
    )
    arena.record_side_result(answered, ArenaRole.CHAMPION, payload=_payload("Answer"))
    answered.conversation.refresh_from_db()
    assert [(m.role, m.content) for m in answered.conversation.messages] == [
        ("user", "First"),
        ("user", "Hello"),
        ("assistant", "Answer"),
    ]

    stopped = ArenaComparisonFactory(
        conversation=ChatConversationFactory(messages=[dangling]),
        input_snapshot={"request_ui_message": question},
    )
    arena.resolve_pending(stopped.conversation, reason="cancelled")
    arena.resolve_pending(stopped.conversation)
    stopped.conversation.refresh_from_db()
    assert [(m.role, m.content) for m in stopped.conversation.messages] == [
        ("user", "First"),
        ("user", "Hello"),
    ]


def test_vote_for_challenger_swaps_the_committed_champion_answer():
    """Preferring the challenger replaces the champion answer, history and usage."""
    comparison = ArenaComparisonFactory(champion_side="left")
    arena.record_side_result(
        comparison,
        ArenaRole.CHAMPION,
        payload=_payload("A", prompt_tokens=10, completion_tokens=20),
    )
    arena.record_side_result(
        comparison,
        ArenaRole.CHALLENGER,
        payload=_payload("B", prompt_tokens=30, completion_tokens=40),
    )

    voted = arena.vote(comparison, "right")

    assert voted.status == ArenaComparisonStatus.VOTED
    assert voted.winner == ArenaRole.CHALLENGER
    assert voted.voted_at is not None
    assert voted.time_to_vote_ms is not None
    conversation = comparison.conversation
    conversation.refresh_from_db()
    assert [m.content for m in conversation.messages] == ["Hello", "B"]
    assert conversation.pydantic_messages[-1]["text"] == "B"
    assert len(conversation.pydantic_messages) == 2
    assert conversation.agent_usage["promptTokens"] == 30
    assert conversation.agent_usage["completionTokens"] == 40


def test_vote_for_champion_keeps_the_committed_answer():
    """Preferring the champion changes nothing in the history, only the vote is stored."""
    comparison = ArenaComparisonFactory(champion_side="left")
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, payload=_payload("B"))

    voted = arena.vote(comparison, "left")

    assert voted.winner == ArenaRole.CHAMPION
    comparison.conversation.refresh_from_db()
    assert [m.content for m in comparison.conversation.messages] == ["Hello", "A"]


def test_vote_requires_both_sides_finished():
    """A vote before both streams finished is a conflict."""
    comparison = ArenaComparisonFactory()
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))

    with pytest.raises(arena.ArenaConflict):
        arena.vote(comparison, "left")


def test_vote_twice_is_a_conflict():
    """A closed comparison refuses a second vote."""
    comparison = ArenaComparisonFactory()
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, payload=_payload("B"))
    arena.vote(comparison, "left")

    with pytest.raises(arena.ArenaConflict):
        arena.vote(comparison, "left")


def test_vote_null_abandons_and_keeps_champion():
    """Abandoning keeps the production answer and never counts as a vote."""
    comparison = ArenaComparisonFactory(champion_side="right")
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, payload=_payload("B"))

    resolved = arena.vote(comparison, None)

    assert resolved.status == ArenaComparisonStatus.ABANDONED
    assert resolved.winner == ""
    comparison.conversation.refresh_from_db()
    assert comparison.conversation.messages[-1].content == "A"


def test_vote_for_errored_side_falls_back_to_champion():
    """Picking a side that failed keeps the champion and closes as errored or abandoned."""
    comparison = ArenaComparisonFactory(champion_side="left")
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, error="model_connection_error")

    resolved = arena.vote(comparison, "right")

    assert resolved.status == ArenaComparisonStatus.ERRORED
    comparison.conversation.refresh_from_db()
    assert comparison.conversation.messages[-1].content == "A"


def test_vote_when_other_side_errored_is_not_counted():
    """A vote against an answer that never arrived is stored as errored, not as a win."""
    comparison = ArenaComparisonFactory(champion_side="left")
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, error="model_connection_error")

    resolved = arena.vote(comparison, "left")

    assert resolved.status == ArenaComparisonStatus.ERRORED
    assert resolved.winner == ""
    comparison.conversation.refresh_from_db()
    assert comparison.conversation.messages[-1].content == "A"


def test_resolve_pending_with_unfinished_champion_is_errored():
    """Walking away before the champion finished leaves nothing to keep."""
    comparison = ArenaComparisonFactory()

    resolved = arena.resolve_pending(comparison.conversation)

    assert resolved.status == ArenaComparisonStatus.ERRORED
    assert "unfinished" in resolved.champion_error
    comparison.conversation.refresh_from_db()
    assert comparison.conversation.messages == []


def test_closing_without_champion_answer_keeps_the_user_message():
    """When no answer survives, the question stays in the history, as on a normal turn."""
    question = _payload("unused")["request_ui_message"]
    comparison = ArenaComparisonFactory(input_snapshot={"request_ui_message": question})
    arena.record_side_result(comparison, ArenaRole.CHAMPION, error="unexpected_error")
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, error="unexpected_error")

    resolved = arena.vote(comparison, None)
    arena.resolve_pending(comparison.conversation)

    assert resolved.status == ArenaComparisonStatus.ERRORED
    assert resolved.closed_reason == "candidate_failed"
    comparison.conversation.refresh_from_db()
    assert [(m.role, m.content) for m in comparison.conversation.messages] == [("user", "Hello")]


def test_resolve_pending_without_pending_is_noop():
    """No pending comparison, nothing to resolve."""
    assert arena.resolve_pending(ChatConversationFactory()) is None


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


def test_wilson_interval_known_values():
    """60 of 100 barely separates from a coin flip; 60 of 30-ish does not."""
    low, high = wilson_interval(60, 100)
    assert round(low, 3) == 0.502
    assert round(high, 3) == 0.691
    low, high = wilson_interval(18, 30)
    assert low < 0.5 < high
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_build_results_scoreboard(experiment):
    """Win rate, interval and indicative flag per challenger."""
    experiment.min_votes_for_conclusion = 3
    experiment.save()
    voted = {"experiment": experiment, "status": ArenaComparisonStatus.VOTED}
    ArenaComparisonFactory(**voted, champion_side="left", winner="challenger")
    ArenaComparisonFactory(**voted, champion_side="right", winner="challenger")
    ArenaComparisonFactory(**voted, champion_side="left", winner="champion")
    ArenaComparisonFactory(experiment=experiment, status=ArenaComparisonStatus.ABANDONED)
    ArenaComparisonFactory(experiment=experiment)

    results = build_results(experiment)

    header = results["header"]
    assert header["total"] == 5
    assert header["voted"] == 3
    assert header["abandoned"] == 1
    assert header["pending"] == 1
    row = results["challengers"][0]
    assert row["model_hrid"] == "challenger-model"
    assert row["comparisons"] == 5
    assert row["votes"] == 3
    assert row["wins"] == 2
    assert row["indicative"] is True


def test_experiment_validation_single_active_and_challenger_tools(experiment, settings):
    """Model-level validation: one active experiment, challengers share the champion tools."""
    # BaseModel validates on save, so building is enough to exercise clean().
    other = ArenaExperimentFactory.build(is_active=True, champion_model_hrid="main-model")
    with pytest.raises(ValidationError):
        other.full_clean()

    settings.LLM_CONFIGURATIONS["tooled"] = _make_llm("tooled", tools=["some_tool"])
    challenger = ArenaChallengerFactory.build(experiment=experiment, model_hrid="tooled")
    with pytest.raises(ValidationError):
        challenger.full_clean()

    same_as_champion = ArenaChallengerFactory.build(experiment=experiment, model_hrid="main-model")
    with pytest.raises(ValidationError):
        same_as_champion.full_clean()


def test_tools_stripped_follows_presentation_flag(settings, experiment):
    """The comparison records that side-effect tools were removed when the feature is on."""
    settings.FEATURE_FLAGS = FeatureFlags(
        arena=FeatureToggle.ENABLED, presentation_generation=FeatureToggle.ENABLED
    )
    conversation = ChatConversationFactory()

    with patch("chat.arena._SYSTEM_RANDOM.random", return_value=0.0):
        comparison = arena.draw_comparison(
            conversation=conversation, user=conversation.owner, force_web_search=False
        )

    assert comparison.tools_stripped is True


def test_late_result_after_cancellation_cannot_modify_a_new_turn():
    """An old worker cannot append content or usage after a newer turn finishes."""
    comparison = ArenaComparisonFactory()
    stale = type(comparison).objects.get(pk=comparison.pk)
    arena.vote(comparison, None)
    arena.resolve_pending(comparison.conversation)
    arena.commit_payload(comparison.conversation, _payload("New answer"))
    before = list(comparison.conversation.pydantic_messages)
    arena.record_side_result(stale, ArenaRole.CHAMPION, payload=_payload("Late answer"))
    comparison.refresh_from_db()
    comparison.conversation.refresh_from_db()
    assert comparison.conversation.pydantic_messages == before
    assert not comparison.champion_committed
    assert comparison.champion_payload is None


def test_result_and_vote_reject_a_superseded_conversation_version():
    """A stale pending status alone is insufficient to authorize a commit or swap."""
    comparison = ArenaComparisonFactory()
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, payload=_payload("B"))
    conversation = comparison.conversation
    conversation.arena_version += 1
    conversation.save(update_fields=["arena_version"])
    arena.commit_payload(conversation, _payload("New answer"))
    with pytest.raises(arena.ArenaConflict):
        arena.vote(comparison, "right")
    conversation.refresh_from_db()
    assert conversation.messages[-1].content == "New answer"


def test_result_commit_rolls_back_with_comparison_save():
    """Conversation content and the committed marker share one transaction."""
    comparison = ArenaComparisonFactory()
    payload = _payload("A")
    with patch.object(type(comparison), "save", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError, match="write failed"):
            arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=payload)
    comparison.refresh_from_db()
    comparison.conversation.refresh_from_db()
    assert comparison.conversation.messages == []
    assert not comparison.champion_committed
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    assert comparison.champion_committed


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_results_commit_once():
    """Two stale worker objects cannot append the same champion turn twice."""

    comparison = ArenaComparisonFactory()
    barrier = Barrier(2)

    def finish():
        close_old_connections()
        try:
            worker = type(comparison).objects.get(pk=comparison.pk)
            barrier.wait(timeout=10)
            arena.record_side_result(worker, ArenaRole.CHAMPION, payload=_payload("A"))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: finish(), range(2)))
    comparison.refresh_from_db()
    conversation = comparison.conversation
    assert [m.content for m in conversation.messages] == ["Hello", "A"]
    assert conversation.agent_usage["promptTokens"] == 10


@pytest.mark.django_db(transaction=True)
def test_concurrent_candidate_claims_have_one_winner(experiment):
    """PostgreSQL serializes competing claims before either calls the provider."""

    conversation = ChatConversationFactory()
    comparison = arena.draw_comparison(
        conversation=conversation, user=conversation.owner, force_web_search=False
    )
    barrier = Barrier(2)
    message = UIMessage.model_validate(_payload("A")["request_ui_message"])

    def claim():
        close_old_connections()
        try:
            worker = type(comparison).objects.get(pk=comparison.pk)
            barrier.wait(timeout=10)
            try:
                arena.claim_candidate(worker, ArenaRole.CHAMPION, message)
                return "claimed"
            except arena.ArenaConflict:
                return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: claim(), range(2))) == ["claimed", "conflict"]


@pytest.mark.parametrize("delete_via", ["instance", "queryset", "user"])
def test_deletion_erases_content_and_user_links(delete_via):
    """Keep aggregate metrics, never prompt/answer copies or personal associations."""

    comparison = ArenaComparisonFactory(
        input_snapshot={"prompt": "private question"},
        champion_trace_id="private trace",
    )
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("Private answer"))
    stale = type(comparison).objects.get(pk=comparison.pk)
    if delete_via == "user":
        comparison.user.delete()
    elif delete_via == "queryset":
        ChatConversation.objects.filter(pk=comparison.conversation_id).delete()
    else:
        comparison.conversation.delete()
    arena.record_side_result(stale, ArenaRole.CHALLENGER, payload=_payload("Late private answer"))
    comparison.refresh_from_db()
    assert comparison.conversation_id is None
    assert comparison.user_id is None
    assert comparison.input_snapshot is None
    assert comparison.champion_payload is None
    assert comparison.challenger_payload is None
    assert comparison.champion_trace_id == ""
    assert comparison.status == ArenaComparisonStatus.ERRORED


def test_retention_purge_is_idempotent_and_preserves_metrics():
    """Only content and associations older than 90 days are removed."""

    old = ArenaComparisonFactory(
        drawn_at=timezone.now() - timedelta(days=91),
        champion_payload=_payload("Private"),
        input_snapshot={"prompt": "private"},
        status=ArenaComparisonStatus.VOTED,
        winner=ArenaRole.CHAMPION,
        champion_prompt_tokens=123,
    )
    recent = ArenaComparisonFactory(champion_payload=_payload("Recent"))
    call_command("purge_arena_content")
    call_command("purge_arena_content")
    old.refresh_from_db()
    recent.refresh_from_db()
    assert old.champion_payload is None
    assert old.input_snapshot is None
    assert old.user_id is None
    assert old.conversation_id is None
    assert old.status == ArenaComparisonStatus.VOTED
    assert old.winner == ArenaRole.CHAMPION
    assert old.champion_prompt_tokens == 123
    assert recent.champion_payload is not None


def test_vote_threshold_does_not_imply_sufficient_evidence():
    """51/100 remains indicative: reaching the sample size is not enough."""
    assert _rate_block(51, 100, 100)["indicative"]
    assert not _rate_block(70, 100, 100)["indicative"]


def test_challenger_failure_is_not_abandonment(experiment):
    """A comparison closed because a candidate failed is counted as errored."""
    comparison = ArenaComparisonFactory(experiment=experiment)
    arena.record_side_result(comparison, ArenaRole.CHAMPION, payload=_payload("A"))
    arena.record_side_result(comparison, ArenaRole.CHALLENGER, error="model_connection_error")
    arena.vote(comparison, None)
    results = build_results(experiment)
    assert results["header"]["abandoned"] == 0
    assert results["header"]["errored"] == 1


def test_snapshot_freezes_existing_history_summary_and_files(experiment):
    """Both candidates run on the history and summary frozen at the draw."""
    conversation = ChatConversationFactory(
        pydantic_messages=[{"kind": "request", "parts": []}],
        history_summary="Original summary",
    )
    # Document turns are never drawn: freeze an image, read by a vision challenger.
    ArenaChallengerFactory(experiment=experiment, model_hrid="vision-challenger")
    message = UIMessage(
        id="u1",
        role="user",
        parts=[
            TextUIPart(type="text", text="Original question"),
            FileUIPart(type="file", mediaType="image/png", url="https://example.test/original.png"),
        ],
    )
    comparison = arena.draw_comparison(
        conversation=conversation,
        user=conversation.owner,
        force_web_search=True,
        last_message=message,
    )
    conversation.pydantic_messages = []
    conversation.history_summary = "New summary"
    conversation.save(update_fields=["pydantic_messages", "history_summary"])
    message.parts[0].text = "Changed"
    comparison = arena.claim_candidate(comparison, ArenaRole.CHALLENGER, message)
    frozen = arena.snapshot_conversation(conversation, comparison)
    assert frozen.history_summary == "Original summary"
    assert len(frozen.pydantic_messages) == 1
    assert (
        comparison.input_snapshot["request_ui_message"]["parts"][0]["text"] == "Original question"
    )
    assert comparison.input_snapshot["request_ui_message"]["parts"][1]["url"].endswith(
        "original.png"
    )
    assert comparison.input_snapshot["force_web_search"] is True


@pytest.mark.parametrize(
    ("media_type", "challenger", "eligible"),
    [
        ("application/pdf", "vision-challenger", False),
        ("image/png", "challenger-model", False),
        ("image/png", "vision-challenger", True),
    ],
)
def test_claim_applies_draw_attachment_rules_to_a_late_message(
    experiment, media_type, challenger, eligible
):
    """A draw sent without the message cannot smuggle a document, or an image to a
    text-only challenger, into the candidate runs."""
    comparison = arena.draw_comparison(
        conversation=ChatConversationFactory(), user=UserFactory(), force_web_search=False
    )
    comparison.challenger_model_hrid = challenger
    comparison.save(update_fields=["challenger_model_hrid"])
    message = UIMessage(
        id="u1",
        role="user",
        parts=[
            TextUIPart(type="text", text="Look"),
            FileUIPart(type="file", mediaType=media_type, url="https://example.test/f"),
        ],
    )

    if eligible:
        claimed = arena.claim_candidate(comparison, ArenaRole.CHAMPION, message)
        assert claimed.input_snapshot["request_ui_message"]["parts"][1]["mediaType"] == media_type
    else:
        with pytest.raises(arena.ArenaConflict, match="arena_message_not_eligible"):
            arena.claim_candidate(comparison, ArenaRole.CHAMPION, message)
        comparison.refresh_from_db()
        assert comparison.input_snapshot["request_ui_message"] is None
        assert comparison.champion_started_at is None


def test_older_normal_turn_cannot_roll_back_arena_version(experiment):
    """A normal worker created before the draw cannot overwrite the new turn."""

    conversation = ChatConversationFactory()
    service = AIAgentService(conversation=conversation, user=conversation.owner)
    comparison = arena.draw_comparison(
        conversation=conversation, user=conversation.owner, force_web_search=False
    )
    service.conversation.messages = [
        UIMessage.model_validate(_payload("Old answer")["output_ui_message"])
    ]
    assert service._save_completed_conversation() is False
    conversation.refresh_from_db()
    assert conversation.arena_version == comparison.conversation_version
    assert conversation.messages == []
