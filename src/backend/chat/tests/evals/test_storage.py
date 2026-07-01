"""Tests for eval run storage helpers."""

import json

from chat.evals.storage import get_git_meta, resolve_run, set_baseline


def test_get_git_meta_from_env(monkeypatch):
    """Host-injected git metadata takes precedence over in-container git."""
    monkeypatch.setenv("EVAL_GIT_COMMIT", "abc123def456")
    monkeypatch.setenv("EVAL_GIT_BRANCH", "feature/evals")
    monkeypatch.setenv("EVAL_GIT_DIRTY", "1")

    meta = get_git_meta()

    assert meta == {
        "commit": "abc123def456",
        "commit_short": "abc123d",
        "branch": "feature/evals",
        "dirty": True,
    }


def test_get_git_meta_ignores_empty_env(monkeypatch):
    """Empty EVAL_GIT_COMMIT falls back to subprocess git (may return nulls)."""
    monkeypatch.delenv("EVAL_GIT_COMMIT", raising=False)
    monkeypatch.delenv("EVAL_GIT_BRANCH", raising=False)
    monkeypatch.delenv("EVAL_GIT_DIRTY", raising=False)

    meta = get_git_meta()

    assert "commit" in meta
    assert "branch" in meta
    assert "dirty" in meta


def test_set_baseline_copies_run_snapshot(tmp_path, monkeypatch):
    """Promoting a baseline commits a snapshot under baselines/, not runs/."""
    evals_root = tmp_path / "evals"
    runs_dir = evals_root / "runs"
    baselines_dir = evals_root / "baselines"
    runs_dir.mkdir(parents=True)
    baselines_dir.mkdir(parents=True)

    run_record = {
        "run_id": "2026-06-17T14-56-06Z_nogit",
        "created_at": "2026-06-17T14:56:06.125374+00:00",
        "git": {"commit_short": "abc1234"},
        "params": {"model_hrid": "test-model"},
        "summary": {"overall_pass_rate": 0.5},
        "datasets": {},
    }
    run_path = runs_dir / f"{run_record['run_id']}.json"
    run_path.write_text(json.dumps(run_record), encoding="utf-8")
    index_path = runs_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "runs": [{"run_id": run_record["run_id"], "file": f"runs/{run_path.name}"}],
                "baselines": {},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("chat.evals.storage.EVALS_ROOT", evals_root)
    monkeypatch.setattr("chat.evals.storage.RUNS_DIR", runs_dir)
    monkeypatch.setattr("chat.evals.storage.BASELINES_DIR", baselines_dir)
    monkeypatch.setattr("chat.evals.storage.INDEX_PATH", index_path)

    baseline = set_baseline(
        run_ref=run_record["run_id"], baseline_name="main", label="Baseline main"
    )

    snapshot_path = baselines_dir / "main_run.json"
    assert snapshot_path.is_file()
    assert baseline["run_file"] == "baselines/main_run.json"
    assert json.loads(snapshot_path.read_text(encoding="utf-8"))["run_id"] == run_record["run_id"]

    run_path.unlink()
    index_path.unlink()

    resolved, resolved_path = resolve_run(run_record["run_id"])
    assert resolved["run_id"] == run_record["run_id"]
    assert resolved_path == snapshot_path
