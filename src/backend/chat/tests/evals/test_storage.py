"""Tests for eval run storage helpers."""

from chat.evals.storage import get_git_meta


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
