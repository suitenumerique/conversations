"""Aggregations behind the arena results page.

Everything here is read-only and deliberately simple: every vote is a challenger
against the same champion, so a sorted win-rate table is the scoreboard and no
pairwise ranking model is needed. Win rates come with a Wilson score interval and
an "indicative" flag while the sample is small or its interval includes 50%.
The flag is a label, never a gate: the numbers are always shown.
"""

import math
from collections import defaultdict

from chat import models
from chat.arena import get_refused_draws
from chat.enums import ArenaComparisonStatus, ArenaRole

Z_95 = 1.96


def wilson_interval(wins: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """95 percent Wilson score interval of a proportion, as (low, high) in [0, 1]."""
    if total <= 0:
        return (0.0, 0.0)
    p_hat = wins / total
    denominator = 1 + z**2 / total
    centre = (p_hat + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(p_hat * (1 - p_hat) / total + z**2 / (4 * total**2)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _rate_block(wins: int, total: int, threshold: int) -> dict:
    low, high = wilson_interval(wins, total)
    return {
        "votes": total,
        "wins": wins,
        "win_rate": wins / total if total else None,
        "ci_low": low if total else None,
        "ci_high": high if total else None,
        "indicative": total < threshold or low <= 0.5 <= high,
    }


def build_results(experiment: models.ArenaExperiment) -> dict:
    """Compute every number the results template renders for one experiment."""
    comparisons = list(
        experiment.comparisons.only("status", "winner", "challenger_model_hrid", "experiment_id")
    )
    threshold = experiment.min_votes_for_conclusion

    by_status = defaultdict(int)
    for comparison in comparisons:
        by_status[comparison.status] += 1
    header = {
        "total": len(comparisons),
        "voted": by_status[ArenaComparisonStatus.VOTED],
        "abandoned": by_status[ArenaComparisonStatus.ABANDONED],
        "errored": by_status[ArenaComparisonStatus.ERRORED],
        "pending": by_status[ArenaComparisonStatus.PENDING],
        "refused_draws": get_refused_draws(experiment.pk),
        "threshold": threshold,
    }

    # Challenger table, sorted by win rate: the scoreboard. Challengers removed from
    # the experiment keep their row as long as they have comparisons.
    hrids = sorted(
        set(experiment.challengers.values_list("model_hrid", flat=True))
        | {c.challenger_model_hrid for c in comparisons}
    )
    challengers = []
    for hrid in hrids:
        rows = [c for c in comparisons if c.challenger_model_hrid == hrid]
        votes = [c for c in rows if c.status == ArenaComparisonStatus.VOTED]
        wins = sum(1 for c in votes if c.winner == ArenaRole.CHALLENGER)
        challengers.append(
            {
                "model_hrid": hrid,
                "comparisons": len(rows),
                **_rate_block(wins, len(votes), threshold),
            }
        )
    challengers.sort(key=lambda row: (row["win_rate"] is None, -(row["win_rate"] or 0)))

    return {"header": header, "challengers": challengers}
