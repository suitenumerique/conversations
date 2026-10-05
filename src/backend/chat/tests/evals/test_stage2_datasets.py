"""Integrity of the stage 2 regression datasets: case mix, graded checks, fixtures, sizes."""

import re
from types import SimpleNamespace

import pytest
import yaml

from chat.evals.configs import REGISTRY
from chat.evals.evaluators.text_checks import Regex, normalize
from chat.tokens import count_approx_tokens

FIXTURES_DIR = REGISTRY["multi_doc_synthesis"].dataset_path.with_suffix("")
PASTE_RE = re.compile(r"\{\{paste:([\w-]+)\}\}")
LABEL_ONLY = {"ToolsUsed"}
# Conversation budget on current code ≈ int(131072 × 0.8) − 1000 − system prompt ≈ 101k;
# v0.0.21 (2508) must still fit the whole history in its 128k context.
SUMMARY_WINDOW = (103_000, 118_000)
CONTROL_MAX = 70_000
EXPECTED_CASES = {
    "chat_instructions": 20,
    "web_search": 7,
    "project_instructions": 7,
    "long_chat": 4,
}


def _cases(name: str) -> list[dict]:
    return yaml.safe_load(REGISTRY[name].dataset_path.read_text(encoding="utf-8"))["cases"]


def _turns(case: dict) -> list[str]:
    return [case["inputs"]["user_message"], *case["inputs"].get("follow_ups", [])]


def _expanded_tokens(text: str) -> int:
    return count_approx_tokens(
        PASTE_RE.sub(lambda m: (FIXTURES_DIR / f"{m.group(1)}.md").read_text("utf-8"), text)
    )


@pytest.mark.parametrize(("name", "count"), EXPECTED_CASES.items())
def test_case_count_and_unique_names(name, count):
    """Each dataset has the spec's number of cases, with unique names."""
    names = [case["name"] for case in _cases(name)]

    assert len(names) == count
    assert len(set(names)) == count


@pytest.mark.parametrize("name", EXPECTED_CASES)
def test_every_case_has_a_graded_evaluator(name):
    """A label alone never passes a case."""
    for case in _cases(name):
        graded = [
            evaluator
            for evaluator in case.get("evaluators", [])
            if (next(iter(evaluator)) if isinstance(evaluator, dict) else evaluator)
            not in LABEL_ONLY
        ]
        assert graded, case["name"]


@pytest.mark.parametrize("name", EXPECTED_CASES)
def test_referenced_fixtures_exist(name):
    """Pasted and project fixtures exist."""
    for case in _cases(name):
        names = PASTE_RE.findall(" ".join(_turns(case)))
        names += case["inputs"].get("project_attachments", [])
        for fixture in names:
            assert (FIXTURES_DIR / f"{fixture}.md").is_file(), f"{case['name']}: {fixture}"


def test_project_facts_appear_in_project_documents():
    """FactRecall facts of project cases come from the project's documents."""
    for case in _cases("project_instructions"):
        documents = case["inputs"].get("project_attachments", [])
        if not documents:
            continue
        corpus = normalize(
            " ".join((FIXTURES_DIR / f"{doc}.md").read_text("utf-8") for doc in documents)
        )
        for evaluator in case["evaluators"]:
            for fact in (evaluator.get("FactRecall") or {}).get("facts", []):
                assert normalize(fact) in corpus, f"{case['name']}: {fact}"


def test_project_cases_all_run_in_a_project():
    """Every project case declares instructions or documents (otherwise no project is made)."""
    for case in _cases("project_instructions"):
        inputs = case["inputs"]
        assert inputs.get("project_instructions") or inputs.get("project_attachments"), case["name"]


def test_long_chat_history_sits_in_the_summary_window():
    """Before the scored turn, history crosses the summary budget but fits v0.0.21's context;
    the control case stays well under budget."""
    for case in _cases("long_chat"):
        history = sum(_expanded_tokens(text) for text in _turns(case)[:-1])
        expected = case["inputs"]["expect_history_summary"]
        if expected:
            assert SUMMARY_WINDOW[0] <= history <= SUMMARY_WINDOW[1], (case["name"], history)
        else:
            assert history <= CONTROL_MAX, (case["name"], history)


def test_chat_instructions_mix():
    """16 single-turn and 4 multi-turn chat cases, none with attachments."""
    cases = _cases("chat_instructions")
    multi = [case for case in cases if case["inputs"].get("follow_ups")]

    assert len(multi) == 4
    assert not any(case["inputs"].get("attachments") for case in cases)


def _case(name: str, case_name: str) -> dict:
    return next(case for case in _cases(name) if case["name"] == case_name)


def _evaluator_args(case: dict, evaluator: str) -> dict:
    return next(entry[evaluator] for entry in case["evaluators"] if evaluator in entry)


def test_mail_formel_subject_must_open_the_answer():
    """The « Objet : » line is required first, not anywhere in the mail."""
    regex = Regex(**_evaluator_args(_case("chat_instructions", "mail_formel"), "Regex"))

    assert regex.evaluate(SimpleNamespace(output="**Objet :** Report\n\nMonsieur")).value
    assert not regex.evaluate(SimpleNamespace(output="Monsieur,\nObjet : report")).value


def test_urls_inventees_requires_at_least_one_link():
    """An answer without any link must not pass the "no invented URL" case."""
    case = _case("web_search", "urls_inventees")

    assert _evaluator_args(case, "UrlCount") == {"minimum": 1}
