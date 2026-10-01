"""Unit tests for the thank-you block returned with an arena vote."""

import pytest

from core.factories import UserFactory

from chat import arena
from chat.enums import ArenaComparisonStatus
from chat.factories import ArenaComparisonFactory, ArenaExperimentFactory

pytestmark = pytest.mark.django_db


def _voted(**kwargs):
    return ArenaComparisonFactory(status=ArenaComparisonStatus.VOTED, **kwargs)


def test_acknowledgement_counts_user_and_experiment_votes():
    """``user_votes`` spans every experiment of the user; ``experiment_votes`` every user."""
    user = UserFactory()
    experiment = ArenaExperimentFactory()
    other_experiment = ArenaExperimentFactory()
    comparison = _voted(user=user, experiment=experiment)
    _voted(user=user, experiment=experiment)
    _voted(user=user, experiment=other_experiment)
    _voted(user=UserFactory(), experiment=experiment)
    # Not votes: pending, abandoned, errored, and a redacted (user-less) vote.
    ArenaComparisonFactory(user=user, experiment=experiment)
    ArenaComparisonFactory(user=user, experiment=experiment, status=ArenaComparisonStatus.ABANDONED)
    ArenaComparisonFactory(user=user, experiment=experiment, status=ArenaComparisonStatus.ERRORED)
    _voted(user=None, experiment=other_experiment)

    block = arena.build_acknowledgement(comparison, user)

    assert block == {"user_votes": 3, "experiment_votes": 3, "milestone": None}


@pytest.mark.parametrize(
    ("votes", "milestone"),
    [(1, "first_vote"), (2, None), (10, "tenth_vote"), (11, None), (100, "hundredth_vote")],
)
def test_acknowledgement_milestones(votes, milestone):
    """Milestones fire on the first, tenth and hundredth vote only."""
    user = UserFactory()
    experiment = ArenaExperimentFactory()
    comparison = _voted(user=user, experiment=experiment)
    for _ in range(votes - 1):
        _voted(user=user, experiment=experiment)

    block = arena.build_acknowledgement(comparison, user)

    assert block["user_votes"] == votes
    assert block["milestone"] == milestone


@pytest.mark.parametrize("status", [ArenaComparisonStatus.ABANDONED, ArenaComparisonStatus.ERRORED])
def test_no_acknowledgement_without_a_vote(status):
    """Abandonment (or a comparison closed as errored) returns no block."""
    comparison = ArenaComparisonFactory(status=status)

    assert arena.build_acknowledgement(comparison, comparison.user) is None
