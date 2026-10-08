"""Tests for the run_evals management command helpers."""
# pylint: disable=protected-access

from django.core.management.base import CommandError

import pytest
from pydantic_evals.evaluators import LLMJudge

from chat.evals import served_model
from chat.evals.configs import REGISTRY
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
    return {"dataset": None, "case": None, "save": False, "model": None, **overrides}


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
