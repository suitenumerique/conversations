"""Integrity of the conversation datasets: case mix, graded checks, fixtures and sizes."""

import re
from types import SimpleNamespace

import pytest
import yaml

from chat.evals.configs import REGISTRY
from chat.evals.configs.conversation import DOCUMENTS_DIR
from chat.evals.evaluators.text_checks import Regex, normalize
from chat.tokens import compute_document_budget, count_approx_tokens

PASTE_RE = re.compile(r"\{\{paste:([\w-]+)\}\}")
LABEL_ONLY = {"ToolsUsed"}
EXPECTED_CASES = {
    "chat_instructions": 20,
    "web_search": 7,
    "multi_doc_synthesis": 29,
    "project_instructions": 7,
    "long_chat": 4,
    "kiwi": 5,
    "claude_style": 8,
}
# Document budget of an eval run: the compared models' max_token_context
# (MODEL_COMPARISON.md) and the dev and prod DOCUMENT_CONTEXT_BUDGET_RATIO (the test
# settings use another one). The short/long split below only holds for them.
MAX_TOKEN_CONTEXT = 131_072
BUDGET_RATIO = 0.2
SECURITY_BUFFER_TOKENS = 1_000
SHORT = [f"court-cr-0{index}" for index in range(1, 5)]
LONG = [f"long-cr-0{index}" for index in range(1, 5)]
# Pipeline check case (one fact, one tiny document), outside the 28-case matrix.
SMOKE_CASE = "smoke_responsable"


def _cases(name: str) -> list[dict]:
    return yaml.safe_load(REGISTRY[name].dataset_path.read_text(encoding="utf-8"))["cases"]


def _case(name: str, case_name: str) -> dict:
    return next(case for case in _cases(name) if case["name"] == case_name)


def _evaluator_args(case: dict, evaluator: str) -> dict:
    return next(entry[evaluator] for entry in case["evaluators"] if evaluator in entry)


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


@pytest.mark.parametrize(("name", "count"), EXPECTED_CASES.items())
def test_case_count_and_unique_names(name, count):
    """Each dataset has its number of cases, with unique names."""
    names = [case["name"] for case in _cases(name)]

    assert len(names) == count
    assert len(set(names)) == count


@pytest.mark.parametrize("name", EXPECTED_CASES)
def test_every_case_is_graded(name):
    """A label alone never passes a case: each case, or its dataset, has a graded evaluator."""
    dataset = yaml.safe_load(REGISTRY[name].dataset_path.read_text(encoding="utf-8"))
    dataset_graded = [
        evaluator
        for evaluator in dataset.get("evaluators", [])
        if (next(iter(evaluator)) if isinstance(evaluator, dict) else evaluator) not in LABEL_ONLY
    ]
    for case in dataset["cases"]:
        graded = [
            evaluator
            for evaluator in case.get("evaluators", [])
            if (next(iter(evaluator)) if isinstance(evaluator, dict) else evaluator)
            not in LABEL_ONLY
        ]
        assert graded or dataset_graded, case["name"]


@pytest.mark.parametrize("name", EXPECTED_CASES)
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


def test_multi_doc_synthesis_case_mix():
    """20 single-turn cases (10 per set) and 8 multi-turn (6 long, 2 short)."""
    cases = [case for case in _cases("multi_doc_synthesis") if case["name"] != SMOKE_CASE]
    single = [case for case in cases if not case["inputs"].get("follow_ups")]
    multi = [case for case in cases if case["inputs"].get("follow_ups")]

    assert sorted(case["metadata"]["doc_set"] for case in single) == ["long"] * 10 + ["short"] * 10
    assert sorted(case["metadata"]["doc_set"] for case in multi) == ["long"] * 6 + ["short"] * 2


def test_doc_set_matches_attachments():
    """doc_set tags agree with the fixtures actually attached."""
    expected = {"short": SHORT, "long": LONG}
    for case in _cases("multi_doc_synthesis"):
        if case["name"] == SMOKE_CASE:
            continue
        assert case["inputs"]["attachments"] == expected[case["metadata"]["doc_set"]], case["name"]


def test_project_cases_all_run_in_a_project():
    """Every project case declares instructions or documents (otherwise there is no project)."""
    for case in _cases("project_instructions"):
        inputs = case["inputs"]
        assert inputs.get("project_instructions") or inputs.get("project_attachments"), case["name"]


def test_chat_instructions_mix():
    """16 single-turn and 4 multi-turn chat cases, none with attachments."""
    cases = _cases("chat_instructions")
    multi = [case for case in cases if case["inputs"].get("follow_ups")]

    assert len(multi) == 4
    assert not any(case["inputs"].get("attachments") for case in cases)


def test_long_chat_states():
    """Summarized cases start from a summary and the recent turns production keeps; the
    control keeps its whole, under-budget history and has no summary."""
    for case in _cases("long_chat"):
        inputs = case["inputs"]
        roles = [message["role"] for message in inputs["message_history"]]
        assert roles == ["user", "assistant"] * 3, case["name"]
        if case["name"] == "controle_sous_budget":
            assert "history_summary" not in inputs
        else:
            assert inputs["history_summary"], case["name"]


def test_mail_formel_subject_must_open_the_answer():
    """The « Objet : » line is required first, not anywhere in the mail."""
    regex = Regex(**_evaluator_args(_case("chat_instructions", "mail_formel"), "Regex"))

    assert regex.evaluate(SimpleNamespace(output="**Objet :** Report\n\nMonsieur")).value
    assert not regex.evaluate(SimpleNamespace(output="Monsieur,\nObjet : report")).value


def test_urls_inventees_requires_at_least_one_link():
    """An answer without any link must not pass the "no invented URL" case."""
    case = _case("web_search", "urls_inventees")

    assert _evaluator_args(case, "UrlCount") == {"minimum": 1}
