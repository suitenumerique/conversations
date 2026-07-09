"""Tests for the history-summarization claim on ChatConversation."""

from datetime import timedelta

from django.utils import timezone

import pytest

from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


def test_claim_succeeds_when_unclaimed():
    """Claim is granted and recorded when no prior claim exists."""
    conversation = ChatConversationFactory()
    assert conversation.claim_history_summarization() is True
    conversation.refresh_from_db()
    assert conversation.history_summary_claimed_at is not None
    assert conversation.history_summarization_claim_is_live


def test_claim_fails_while_another_claim_is_live():
    """A second concurrent claim is rejected while the first is still active."""
    conversation = ChatConversationFactory()
    assert conversation.claim_history_summarization() is True
    other = type(conversation).objects.get(pk=conversation.pk)
    assert other.claim_history_summarization() is False


def test_claim_succeeds_over_an_expired_claim():
    """A claim older than the TTL belongs to a provably dead worker."""
    conversation = ChatConversationFactory(
        history_summary_claimed_at=timezone.now() - timedelta(seconds=181)
    )
    assert not conversation.history_summarization_claim_is_live
    assert conversation.claim_history_summarization() is True


def test_release_clears_the_claim():
    """Releasing a claim sets history_summary_claimed_at back to None."""
    conversation = ChatConversationFactory()
    conversation.claim_history_summarization()
    conversation.release_history_summarization_claim()
    conversation.refresh_from_db()
    assert conversation.history_summary_claimed_at is None


def test_release_is_a_noop_when_another_worker_reclaimed():
    """A stale worker's release must not wipe a newer worker's live claim."""
    conversation = ChatConversationFactory()
    conversation.claim_history_summarization()

    # A second worker reclaims (e.g. after the first worker's TTL elapsed).
    reclaimed_at = timezone.now()
    other = type(conversation).objects.get(pk=conversation.pk)
    type(other).objects.filter(pk=other.pk).update(history_summary_claimed_at=reclaimed_at)

    # The first worker releases: it no longer owns the claim, so this is a no-op.
    conversation.release_history_summarization_claim()

    conversation.refresh_from_db()
    assert conversation.history_summary_claimed_at == reclaimed_at


def test_persist_history_summary_advances_checkpoint():
    """Persisting a summary with a newer checkpoint succeeds and saves both fields."""
    conversation = ChatConversationFactory()
    assert conversation.persist_history_summary("a summary", 4) is True
    conversation.refresh_from_db()
    assert conversation.history_summary == "a summary"
    assert conversation.history_summary_checkpoint == 4


def test_persist_history_summary_rejects_stale_checkpoint():
    """Late/duplicate task completions must be no-ops (write-back guard)."""
    conversation = ChatConversationFactory(history_summary="newer", history_summary_checkpoint=6)
    assert conversation.persist_history_summary("older", 6) is False
    assert conversation.persist_history_summary("older", 4) is False
    conversation.refresh_from_db()
    assert conversation.history_summary == "newer"
    assert conversation.history_summary_checkpoint == 6
