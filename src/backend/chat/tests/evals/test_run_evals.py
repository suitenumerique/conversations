"""Tests for the run_evals management command helpers."""
# pylint: disable=protected-access

from django.core.management.base import CommandError

import pytest
from pydantic_evals.evaluators import LLMJudge

from chat.evals import served_model
from chat.evals.configs import REGISTRY
from chat.evals.target.runtime import Target
from chat.management.commands.run_evals import Command


def test_dataset_case_names_lists_declared_cases():
    """_dataset_case_names returns the case names declared in the dataset YAML."""
    names = Command._dataset_case_names(REGISTRY["url_hallucination"])

    assert "easy_docs_link" in names


def test_case_filter_selects_only_datasets_containing_the_case():
    """A --case filter without --dataset keeps only datasets that define the case,
    silently skipping the others (instead of aborting on the first mismatch)."""
    case_name = "easy_docs_link"

    matching = [
        config for config in REGISTRY.values() if case_name in Command._dataset_case_names(config)
    ]

    assert [config.name for config in matching] == ["url_hallucination"]


def test_without_llm_judges_strips_dataset_and_case_judges():
    """--no-llm-judge must drop every LLMJudge, including the per-case ones in the YAML."""
    dataset = Command()._load_dataset(REGISTRY["chat_instructions"], None)
    assert any(isinstance(e, LLMJudge) for case in dataset.cases for e in case.evaluators)

    Command._without_llm_judges(dataset)

    evaluators = [*dataset.evaluators, *(e for case in dataset.cases for e in case.evaluators)]
    assert evaluators
    assert not any(isinstance(e, LLMJudge) for e in evaluators)


def _options(**overrides):
    return {
        "dataset": None,
        "case": None,
        "save": False,
        "model": None,
        "target_url": None,
        "target_tag": None,
        "target_model": None,
        **overrides,
    }


TARGET = Target(url="http://host.docker.internal:18071", tag="v0.0.21", model="default-model")


def test_save_allowed_with_dataset_but_not_with_case():
    """Single-dataset runs can be saved; runs missing cases cannot."""
    Command._check_save_options(_options(save=True, dataset="url_hallucination"))

    with pytest.raises(CommandError):
        Command._check_save_options(_options(save=True, case="x"))


def test_resolve_model_overrides_the_default_model(settings):
    """--model becomes the process's default model, read by every task and the judge."""
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    hrid = next(h for h in settings.LLM_CONFIGURATIONS if h != "default-model")

    assert Command._resolve_model(_options(model=hrid)) == hrid
    assert settings.LLM_DEFAULT_MODEL_HRID == hrid


def test_resolve_model_keeps_the_default_and_rejects_unknown_models(settings):
    """Without --model the default model is tested; an unknown HRID is a usage error."""
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"

    assert Command._resolve_model(_options()) == "default-model"
    with pytest.raises(CommandError, match="Unknown model"):
        Command._resolve_model(_options(model="no-such-model"))


def test_report_served_model_warns_on_an_alias(settings, monkeypatch):
    """A provider answering with another model name is reported; a version suffix is not."""
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    requested = settings.LLM_CONFIGURATIONS["default-model"].model_name
    lines = []

    monkeypatch.setattr(served_model, "served_model", lambda _hrid: f"{requested}-0")
    assert served_model.report_served_model("default-model", write=lines.append) == f"{requested}-0"
    assert not any("WARNING" in line for line in lines)

    monkeypatch.setattr(served_model, "served_model", lambda _hrid: "other-model")
    served_model.report_served_model("default-model", write=lines.append)
    assert lines[-1] == f"WARNING: the provider serves {requested} as other-model\n"


def test_resolve_target_requires_all_three_options():
    """A half-specified target could not be attributed to a git ref: usage error."""
    with pytest.raises(CommandError, match="--target-url, --target-tag and --target-model"):
        Command._resolve_target(_options(target_url=TARGET.url))


def test_resolve_target_builds_target():
    """All three options give a Target; none gives None."""
    options = _options(target_url=TARGET.url, target_tag="v0.0.21", target_model="default-model")

    assert Command._resolve_target(options) == TARGET
    assert Command._resolve_target(_options()) is None


def test_resolve_target_rejects_a_ref_without_known_release():
    """A SHA or branch has no known wire format: refused before anything runs."""
    options = _options(target_url=TARGET.url, target_tag="feature/x", target_model="default-model")

    with pytest.raises(CommandError, match="unknown target ref feature/x"):
        Command._resolve_target(options)


def test_resolve_model_defaults_to_the_target_model_and_rejects_another(settings):
    """On a git ref, the tested model is the stack's; another --model is a usage error."""
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    hrid = next(h for h in settings.LLM_CONFIGURATIONS if h != "default-model")

    assert Command._resolve_model(_options(), TARGET) == "default-model"
    with pytest.raises(CommandError, match="differs from --target-model"):
        Command._resolve_model(_options(model=hrid), TARGET)


def _names(configs) -> list[str]:
    return [config.name for config in configs]


def test_selected_configs_runs_every_dataset_on_the_working_tree():
    """Without a git ref, every dataset runs in-process."""
    configs, skipped = Command._selected_configs(_options(), None)

    assert _names(configs) == list(REGISTRY)
    assert skipped == []


def test_selected_configs_skips_working_tree_only_datasets_on_a_ref():
    """A git ref's stack is only reachable over HTTP: datasets without an HTTP task are skipped."""
    configs, skipped = Command._selected_configs(_options(), TARGET)

    assert sorted(skipped) == ["faithfulness_rag", "long_chat", "tool_selection"]
    assert "url_hallucination" in _names(configs)
    assert not set(skipped) & set(_names(configs))


def test_selected_configs_refuses_a_working_tree_only_dataset_on_a_ref():
    """Asking for a stub-based dataset on a git ref is a usage error."""
    with pytest.raises(CommandError, match="only runs on the working tree"):
        Command._selected_configs(_options(dataset="tool_selection"), TARGET)


def test_selected_configs_keeps_an_http_dataset_on_a_ref():
    """With a ref, a dataset with an HTTP task is selected."""
    configs, _ = Command._selected_configs(_options(dataset="multi_doc_synthesis"), TARGET)

    assert _names(configs) == ["multi_doc_synthesis"]
