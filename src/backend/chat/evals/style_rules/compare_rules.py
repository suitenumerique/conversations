"""Compare saved runs of one dataset rule by rule: per-case pass rate of each evaluator.

Usage: python3 compare_rules.py COMMENT [COMMENT ...]
"""

import glob
import json
import sys
from pathlib import Path

# Saved runs (gitignored) and the committed copies in results/.
RUNS = [
    str(Path(__file__).resolve().parent.parent / "runs" / "*.json"),
    str(Path(__file__).resolve().parent / "results" / "*.json"),
]


def _out(*parts) -> None:
    sys.stdout.write(" ".join(str(part) for part in parts) + "\n")


def load(comment):
    """(run params, cases by name) of the saved run whose comment matches."""
    for path in (path for pattern in RUNS for path in glob.glob(pattern)):
        if path.endswith("index.json"):
            continue
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
        if record.get("comment") == comment:
            dataset = next(iter(record["datasets"].values()))
            if dataset.get("failures"):
                sys.exit(
                    f"{comment}: {dataset['failures']} task error(s); pass rates are not valid"
                )
            return record["params"], {case["name"]: case for case in dataset["cases"]}
    sys.exit(f"run not found: {comment}")


def main(comments):
    """Print one row per case and rule, one column per run."""
    runs = [load(comment) for comment in comments]
    # Runs from the earlier HTTP runner (results/) name the git ref they ran on.
    labels = [
        f"{params.get('target_version', 'local')} "
        f"{params.get('target_model') or params['model_hrid']}"
        for params, _ in runs
    ]
    names = sorted(set.intersection(*(set(cases) for _, cases in runs)))
    _out(f"score = average over {runs[0][0]['runs_per_case']} repeats; - = rule not checked")
    for comment in comments:
        _out(f"  {comment}")
    _out()
    _out("case".ljust(36), "rule".ljust(22), " ".join(label[-34:].rjust(34) for label in labels))
    for name in names:
        rules = sorted({rule for _, cases in runs for rule in cases[name]["avg_scores"]})
        for rule in rules:
            scores = [cases[name]["avg_scores"].get(rule) for _, cases in runs]
            cells = " ".join(("-" if s is None else f"{s:.0%}").rjust(34) for s in scores)
            _out(name[:36].ljust(36), rule[:22].ljust(22), cells)
        _out()
    _summary(runs, names)


def _mean(values):
    return sum(values) / len(values) if values else None


def _cell(score) -> str:
    return ("-" if score is None else f"{score:.0%}").rjust(34)


def _summary(runs, names):
    """Each rule averaged over the compared cases, then all rules together.

    A case passes only if every rule holds, so its pass rate hides a model that breaks one
    rule less often than another; this average does not.
    """
    rules = sorted(
        {rule for _, cases in runs for name in names for rule in cases[name]["avg_scores"]}
    )
    _out("all cases".ljust(36), "(rule average)".ljust(22))
    for rule in rules:
        scores = [
            _mean(
                [
                    cases[name]["avg_scores"][rule]
                    for name in names
                    if rule in cases[name]["avg_scores"]
                ]
            )
            for _, cases in runs
        ]
        _out("".ljust(36), rule[:22].ljust(22), " ".join(_cell(score) for score in scores))
    compliance = [
        _mean([score for name in names for score in cases[name]["avg_scores"].values()])
        for _, cases in runs
    ]
    _out("".ljust(36), "all rules".ljust(22), " ".join(_cell(score) for score in compliance))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1:])
