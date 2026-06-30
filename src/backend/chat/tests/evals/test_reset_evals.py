"""Tests for eval storage reset."""

import json

from chat.evals.storage import reset_eval_artifacts


def test_reset_eval_artifacts_clears_runs_baselines_and_dashboard(tmp_path, monkeypatch):
    """Test that the eval artifacts are cleared when the reset_eval_artifacts function is called."""
    runs_dir = tmp_path / "runs"
    baselines_dir = tmp_path / "baselines"
    dashboard_dir = tmp_path / "dashboard"
    runs_dir.mkdir()
    baselines_dir.mkdir()
    dashboard_dir.mkdir()

    (runs_dir / "2026-01-01T00-00-00Z_abcd.json").write_text("{}", encoding="utf-8")
    (runs_dir / "index.json").write_text(
        json.dumps({"runs": [{"run_id": "x"}], "baselines": {"main": {}}}),
        encoding="utf-8",
    )
    (baselines_dir / "main.json").write_text("{}", encoding="utf-8")
    (baselines_dir / "main_run.json").write_text("{}", encoding="utf-8")
    (dashboard_dir / "dashboard.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr("chat.evals.storage.RUNS_DIR", runs_dir)
    monkeypatch.setattr("chat.evals.storage.BASELINES_DIR", baselines_dir)
    monkeypatch.setattr("chat.evals.storage.DASHBOARD_DIR", dashboard_dir)
    monkeypatch.setattr("chat.evals.storage.INDEX_PATH", runs_dir / "index.json")

    deleted = reset_eval_artifacts()

    assert deleted["runs"] == ["2026-01-01T00-00-00Z_abcd.json"]
    assert set(deleted["baselines"]) == {"main.json", "main_run.json"}
    assert deleted["dashboard"] == ["dashboard.html"]
    assert list(runs_dir.glob("*.json")) == [runs_dir / "index.json"]
    assert json.loads((runs_dir / "index.json").read_text(encoding="utf-8")) == {
        "runs": [],
        "baselines": {},
    }
    assert not (baselines_dir / "main.json").exists()
    assert not (dashboard_dir / "dashboard.html").exists()


def test_reset_eval_artifacts_keep_baselines(tmp_path, monkeypatch):
    """Test that the eval artifacts are kept when the reset_eval_artifacts function is called."""
    runs_dir = tmp_path / "runs"
    baselines_dir = tmp_path / "baselines"
    runs_dir.mkdir()
    baselines_dir.mkdir()
    (runs_dir / "run.json").write_text("{}", encoding="utf-8")
    (runs_dir / "index.json").write_text(
        json.dumps(
            {
                "runs": [{"run_id": "run", "is_baseline": False}],
                "baselines": {"main": {"run_id": "baseline-run"}},
            }
        ),
        encoding="utf-8",
    )
    (baselines_dir / "main.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("chat.evals.storage.RUNS_DIR", runs_dir)
    monkeypatch.setattr("chat.evals.storage.BASELINES_DIR", baselines_dir)
    monkeypatch.setattr("chat.evals.storage.DASHBOARD_DIR", tmp_path / "dashboard")
    monkeypatch.setattr("chat.evals.storage.INDEX_PATH", runs_dir / "index.json")

    deleted = reset_eval_artifacts(runs=True, baselines=False, dashboard=False)

    assert deleted["runs"] == ["run.json"]
    assert not deleted["baselines"]
    assert (baselines_dir / "main.json").exists()
    index = json.loads((runs_dir / "index.json").read_text(encoding="utf-8"))
    assert not index["runs"]
    assert index["baselines"] == {"main": {"run_id": "baseline-run"}}
