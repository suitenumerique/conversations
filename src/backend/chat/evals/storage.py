"""Persist eval runs and baselines as JSON files in the repository."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVALS_ROOT = Path(__file__).resolve().parent
RUNS_DIR = EVALS_ROOT / "runs"
BASELINES_DIR = EVALS_ROOT / "baselines"
DASHBOARD_DIR = EVALS_ROOT / "dashboard"
INDEX_PATH = RUNS_DIR / "index.json"
_JSON_FILE_GLOB = "*.json"

_GIT_EXECUTABLE = shutil.which("git")


def _git_root() -> Path | None:
    if _GIT_EXECUTABLE is None:
        return None
    try:
        return Path(
            subprocess.check_output(  # noqa: S603
                [_GIT_EXECUTABLE, "rev-parse", "--show-toplevel"],
                cwd=EVALS_ROOT,
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError, FileNotFoundError:
        return None


def _run_git(args: list[str]) -> str | None:
    git_root = _git_root()
    if git_root is None or _GIT_EXECUTABLE is None:
        return None
    try:
        return (
            subprocess.check_output(  # noqa: S603
                [_GIT_EXECUTABLE, *args], cwd=git_root
            )
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError, FileNotFoundError:
        return None


def _git_meta_from_env() -> dict[str, Any] | None:
    """Git metadata injected by ``make eval`` from the host (Docker has no .git)."""
    commit = os.environ.get("EVAL_GIT_COMMIT", "").strip()
    if not commit:
        return None
    branch = os.environ.get("EVAL_GIT_BRANCH", "").strip() or None
    dirty = os.environ.get("EVAL_GIT_DIRTY", "").strip() in {"1", "true", "True", "yes"}
    return {
        "commit": commit,
        "commit_short": commit[:7],
        "branch": branch,
        "dirty": dirty,
    }


def get_git_meta() -> dict[str, Any]:
    """Return Git metadata from environment or latest commit."""
    if from_env := _git_meta_from_env():
        return from_env

    commit = _run_git(["rev-parse", "HEAD"])
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    dirty = _run_git(["status", "--porcelain"]) not in (None, "")
    return {
        "commit": commit,
        "commit_short": commit[:7] if commit else None,
        "branch": branch,
        "dirty": dirty,
    }


def hash_dataset(dataset_path: Path) -> str:
    """Compute a hash of a dataset file."""
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def make_run_id(git_short: str | None) -> str:
    """Generate a unique run ID based on timestamp and Git commit short."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    suffix = git_short or "nogit"
    return f"{timestamp}_{suffix}"


def _load_index() -> dict[str, Any]:
    """Load the eval index from disk."""
    if not INDEX_PATH.exists():
        return {"runs": [], "baselines": {}}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def _save_index(index: dict[str, Any]) -> None:
    """Save the eval index to disk."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_run_record(
    *,
    datasets: dict[str, Any],
    params: dict[str, Any],
    comment: str | None = None,
    dataset_paths: dict[str, Path],
) -> dict[str, Any]:
    """Build a run record from datasets, parameters, and comment."""
    git_meta = get_git_meta()
    run_id = make_run_id(git_meta["commit_short"])
    dataset_hashes = {name: hash_dataset(path) for name, path in sorted(dataset_paths.items())}
    # Weighted by case count so a 4-case dataset does not weigh as much as a 50-case one.
    total_cases = sum(data["cases_total"] for data in datasets.values())
    total_passed = sum(data["cases_passed"] for data in datasets.values())
    overall_pass_rate = round(total_passed / total_cases, 4) if total_cases else 0.0

    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "comment": comment,
        "git": git_meta,
        "params": params,
        "dataset_hashes": dataset_hashes,
        "summary": {"overall_pass_rate": overall_pass_rate},
        "datasets": datasets,
    }


def save_run(record: dict[str, Any]) -> Path:
    """Save a run record to disk."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"{record['run_id']}.json"
    run_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    index = _load_index()
    index_entry = {
        "run_id": record["run_id"],
        "file": str(run_path.relative_to(EVALS_ROOT)),
        "created_at": record["created_at"],
        "comment": record.get("comment") or record.get("label"),
        "git_commit": record["git"].get("commit_short"),
        "git_branch": record["git"].get("branch"),
        "model_hrid": record["params"].get("model_hrid"),
        "judge_model_hrid": record["params"].get("judge_model_hrid"),
        "llm_judge": record["params"].get("llm_judge"),
        "runs_per_case": record["params"].get("runs_per_case"),
        "datasets": list(record["datasets"].keys()),
        "overall_pass_rate": record["summary"]["overall_pass_rate"],
        "is_baseline": False,
    }

    index["runs"] = [entry for entry in index["runs"] if entry["run_id"] != record["run_id"]]
    index["runs"].insert(0, index_entry)
    _save_index(index)
    return run_path


def _baseline_run_path(baseline_name: str) -> Path:
    return BASELINES_DIR / f"{baseline_name}_run.json"


def _resolve_baseline_run(run_ref: str) -> tuple[dict[str, Any], Path] | None:
    """Resolve a run id from committed baseline snapshots."""
    for baseline_path in sorted(BASELINES_DIR.glob(_JSON_FILE_GLOB)):
        if baseline_path.name.endswith("_run.json"):
            continue
        meta = json.loads(baseline_path.read_text(encoding="utf-8"))
        if meta.get("run_id") != run_ref:
            continue
        run_path = EVALS_ROOT / meta["run_file"]
        if run_path.exists():
            return json.loads(run_path.read_text(encoding="utf-8")), run_path
    return None


def resolve_run(run_ref: str | None) -> tuple[dict[str, Any], Path]:
    """Resolve a run reference to a run record and path."""
    if run_ref in (None, "latest"):
        index = _load_index()
        if not index["runs"]:
            raise FileNotFoundError("No saved eval runs found.")
        run_ref = index["runs"][0]["run_id"]

    candidate = RUNS_DIR / f"{run_ref}.json"
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8")), candidate

    index = _load_index()
    for entry in index["runs"]:
        if entry["run_id"] == run_ref:
            run_path = EVALS_ROOT / entry["file"]
            return json.loads(run_path.read_text(encoding="utf-8")), run_path

    if from_baseline := _resolve_baseline_run(run_ref):
        return from_baseline

    raise FileNotFoundError(f"No eval run found for reference '{run_ref}'.")


def set_baseline(
    *,
    run_ref: str | None,
    baseline_name: str = "main",
    label: str | None = None,
) -> dict[str, Any]:
    """Set a run reference as a baseline."""
    record, run_path = resolve_run(run_ref)
    baseline_run_path = _baseline_run_path(baseline_name)
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_path, baseline_run_path)
    baseline = {
        "name": baseline_name,
        "label": label
        or record.get("comment")
        or record.get("label")
        or f"Baseline {baseline_name}",
        "created_at": datetime.now(UTC).isoformat(),
        "run_id": record["run_id"],
        "run_file": str(baseline_run_path.relative_to(EVALS_ROOT)),
        "git_commit": record["git"].get("commit_short"),
        "model_hrid": record["params"].get("model_hrid"),
        "judge_model_hrid": record["params"].get("judge_model_hrid"),
    }

    baseline_path = BASELINES_DIR / f"{baseline_name}.json"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    index = _load_index()
    index["baselines"][baseline_name] = baseline
    baseline_run_ids = {meta.get("run_id") for meta in index["baselines"].values()}
    for entry in index["runs"]:
        entry["is_baseline"] = entry["run_id"] in baseline_run_ids
    _save_index(index)
    return baseline


def load_baseline(baseline_name: str = "main") -> dict[str, Any]:
    """Load a baseline from disk."""
    baseline_path = BASELINES_DIR / f"{baseline_name}.json"
    if not baseline_path.exists():
        index = _load_index()
        baseline = index.get("baselines", {}).get(baseline_name)
        if not baseline:
            raise FileNotFoundError(f"No baseline named '{baseline_name}'.")
        return baseline
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def _delete_json_files(
    directory: Path, *, exclude_names: frozenset[str] | None = None
) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    excluded = exclude_names or frozenset()
    deleted: list[str] = []
    for path in sorted(directory.glob(_JSON_FILE_GLOB)):
        if path.name in excluded:
            continue
        path.unlink()
        deleted.append(path.name)
    return deleted


def _delete_dashboard_artifact() -> list[str]:
    dashboard_path = DASHBOARD_DIR / "dashboard.html"
    if not dashboard_path.exists():
        return []
    dashboard_path.unlink()
    return [dashboard_path.name]


def _clear_eval_index(*, runs: bool, baselines: bool) -> None:
    index = _load_index()
    if runs:
        index["runs"] = []
    if baselines:
        index["baselines"] = {}
        for entry in index.get("runs", []):
            entry["is_baseline"] = False
    _save_index(index)


def reset_eval_artifacts(
    *,
    runs: bool = True,
    baselines: bool = True,
    dashboard: bool = True,
) -> dict[str, list[str]]:
    """Delete saved eval runs, baselines, and/or dashboard output.

    Returns a mapping of category → deleted file names (basenames only).
    """
    deleted: dict[str, list[str]] = {"runs": [], "baselines": [], "dashboard": []}

    if runs:
        deleted["runs"] = _delete_json_files(RUNS_DIR, exclude_names=frozenset({"index.json"}))
    if baselines:
        deleted["baselines"] = _delete_json_files(BASELINES_DIR)
    if dashboard:
        deleted["dashboard"] = _delete_dashboard_artifact()
    if runs or baselines:
        _clear_eval_index(runs=runs, baselines=baselines)

    return deleted
