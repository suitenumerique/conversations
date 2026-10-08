"""Integrity of the conversation datasets: graded checks, fixtures and sizes."""

import re

import pytest
import yaml

from chat.evals.configs import REGISTRY
from chat.evals.configs.conversation import DOCUMENTS_DIR
from chat.evals.evaluators.text_checks import normalize
from chat.tokens import compute_document_budget, count_approx_tokens

PASTE_RE = re.compile(r"\{\{paste:([\w-]+)\}\}")
LABEL_ONLY = {"ToolsUsed"}
DATASETS = [
    "chat_instructions",
    "web_search",
    "multi_doc_synthesis",
    "project_instructions",
    "long_chat",
    "kiwi",
    "claude_style",
]
# Document budget of an eval run: the compared models' max_token_context
# (MODEL_COMPARISON.md) and the dev and prod DOCUMENT_CONTEXT_BUDGET_RATIO (the test
# settings use another one). The short/long split below only holds for them.
MAX_TOKEN_CONTEXT = 131_072
BUDGET_RATIO = 0.2
SECURITY_BUFFER_TOKENS = 1_000
SHORT = [f"court-cr-0{index}" for index in range(1, 5)]
LONG = [f"long-cr-0{index}" for index in range(1, 5)]


def _cases(name: str) -> list[dict]:
    return yaml.safe_load(REGISTRY[name].dataset_path.read_text(encoding="utf-8"))["cases"]


def _documents(case: dict) -> list[str]:
    inputs = case["inputs"]
    return [*inputs.get("attachments", []), *inputs.get("project_attachments", [])]


def _pasted(case: dict) -> list[str]:
    return [
        name
        for message in case["inputs"].get("message_history", [])
        for name in PASTE_RE.findall(message["content"])
    ]


def _text(name: str) -> str:
    return (DOCUMENTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _document_budget() -> int:
    return compute_document_budget(MAX_TOKEN_CONTEXT, BUDGET_RATIO, SECURITY_BUFFER_TOKENS)


def _tokens(name: str) -> int:
    return count_approx_tokens(_text(name))


@pytest.mark.parametrize("name", DATASETS)
def test_every_case_is_graded(name):
    """A label alone never passes a case: each case, or its dataset, has a graded evaluator."""
    dataset = yaml.safe_load(REGISTRY[name].dataset_path.read_text(encoding="utf-8"))
    # Dotted paths name the evaluator by their last segment.
    dataset_graded = [
        evaluator
        for evaluator in dataset.get("config", {}).get("extra_evaluators", [])
        if (next(iter(evaluator)) if isinstance(evaluator, dict) else evaluator.rsplit(".")[-1])
        not in LABEL_ONLY
    ]
    for case in dataset["cases"]:
        graded = [
            evaluator
            for evaluator in case.get("evaluators", [])
            if (next(iter(evaluator)) if isinstance(evaluator, dict) else evaluator)
            not in LABEL_ONLY
        ]
        assert graded or dataset_graded, case["name"]


@pytest.mark.parametrize("name", DATASETS)
def test_documents_have_their_text_and_fixed_summary(name):
    """Attached and project documents have a fixture and the summary the stubs return."""
    for case in _cases(name):
        for document in _documents(case):
            assert (DOCUMENTS_DIR / f"{document}.md").is_file(), (case["name"], document)
            assert (DOCUMENTS_DIR / f"{document}.summary.md").is_file(), (case["name"], document)
        for document in _pasted(case):
            assert (DOCUMENTS_DIR / f"{document}.md").is_file(), (case["name"], document)


@pytest.mark.parametrize("name", ["multi_doc_synthesis", "project_instructions"])
def test_reference_facts_appear_in_the_documents(name):
    """A FactRecall fact the documents do not contain would fail every model."""
    for case in _cases(name):
        if not _documents(case):
            continue
        corpus = normalize(" ".join(_text(document) for document in _documents(case)))
        for evaluator in case.get("evaluators", []):
            for fact in (evaluator.get("FactRecall") or {}).get("facts", []):
                assert normalize(fact) in corpus, f"{case['name']}: {fact}"


def test_short_set_is_fully_inlined():
    """The four short reports fit the document budget together (all full-context)."""
    assert sum(_tokens(name) for name in SHORT) <= _document_budget()
    assert all(_tokens(name) <= 2_500 for name in SHORT)


def test_long_set_splits_inline_and_tool_only():
    """Each long report fits alone and two fit together, but three do not.

    FIFO eviction then leaves the two oldest reports tool_call_only, so the
    summarize / RAG path is exercised.
    """
    sizes, budget = [_tokens(name) for name in LONG], _document_budget()

    assert all(budget / 3 < size <= budget / 2 for size in sizes), sizes
