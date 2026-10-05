"""Integrity of the multi_doc_synthesis dataset: fixtures, facts, sizes, case mix."""

from pathlib import Path

import pytest

from chat.evals.configs import REGISTRY
from chat.evals.configs.base import split_dataset_file
from chat.evals.evaluators.text_checks import normalize
from chat.tokens import count_approx_tokens

CONFIG = REGISTRY["multi_doc_synthesis"]
DOCUMENTS_DIR = Path(CONFIG.dataset_path).with_suffix("")
# Prod: max_token_context 128000 (2508) x DOCUMENT_CONTEXT_BUDGET_RATIO 0.2 - 1000.
DOCUMENT_BUDGET = 24_600
SHORT = [f"court-cr-0{index}" for index in range(1, 5)]
# Pipeline check case (one fact, one tiny document), outside the 28-case matrix.
SMOKE_CASE = "smoke_responsable"
LONG = [f"long-cr-0{index}" for index in range(1, 5)]


@pytest.fixture(name="cases")
def cases_fixture():
    """Dataset cases as declared in the YAML."""
    return split_dataset_file(CONFIG.dataset_path)[1]["cases"]


def _tokens(name: str) -> int:
    return count_approx_tokens((DOCUMENTS_DIR / f"{name}.md").read_text(encoding="utf-8"))


def _fact_lists(case: dict) -> list[list[str]]:
    return [
        evaluator["FactRecall"]["facts"]
        for evaluator in case.get("evaluators", [])
        if isinstance(evaluator, dict) and "FactRecall" in evaluator
    ]


def test_every_attachment_exists(cases):
    """Cases only reference fixture documents that exist."""
    for case in cases:
        for name in case["inputs"].get("attachments", []):
            assert (DOCUMENTS_DIR / f"{name}.md").is_file(), f"{case['name']}: {name}"


def test_reference_facts_appear_in_attached_documents(cases):
    """A FactRecall fact the documents do not contain would fail every model."""
    for case in cases:
        corpus = normalize(
            " ".join(
                (DOCUMENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
                for name in case["inputs"].get("attachments", [])
            )
        )
        for facts in _fact_lists(case):
            missing = [fact for fact in facts if normalize(fact) not in corpus]
            assert not missing, f"{case['name']}: facts not in documents: {missing}"


def test_short_set_is_fully_inlined():
    """The four short reports fit the document budget together (all full-context)."""
    assert sum(_tokens(name) for name in SHORT) <= DOCUMENT_BUDGET
    assert all(_tokens(name) <= 2_500 for name in SHORT)


def test_long_set_splits_inline_and_tool_only():
    """Each long report fits alone and two fit together, but three do not.

    FIFO eviction then leaves the two oldest reports tool_call_only, so the
    summarize / RAG path is exercised.
    """
    sizes = [_tokens(name) for name in LONG]

    assert all(DOCUMENT_BUDGET / 3 < size <= DOCUMENT_BUDGET / 2 for size in sizes), sizes


def test_case_mix_matches_spec(cases):
    """20 single-turn cases (10 per set) and 8 multi-turn (6 long, 2 short)."""
    cases = [case for case in cases if case["name"] != SMOKE_CASE]
    single = [case for case in cases if not case["inputs"].get("follow_ups")]
    multi = [case for case in cases if case["inputs"].get("follow_ups")]

    assert sorted(case["metadata"]["doc_set"] for case in single) == ["long"] * 10 + ["short"] * 10
    assert sorted(case["metadata"]["doc_set"] for case in multi) == ["long"] * 6 + ["short"] * 2


def test_doc_set_matches_attachments(cases):
    """doc_set tags agree with the fixtures actually attached."""
    expected = {"short": SHORT, "long": LONG}
    for case in cases:
        if case["name"] == SMOKE_CASE:
            continue
        assert case["inputs"]["attachments"] == expected[case["metadata"]["doc_set"]], case["name"]


def test_each_case_has_a_graded_evaluator(cases):
    """Every case is graded by at least one assertion (labels alone never pass a case)."""
    for case in cases:
        assert case.get("evaluators"), case["name"]
