"""Tests for the run_evals management command helpers."""
# pylint: disable=protected-access

from django.core.management.base import CommandError

import pytest

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


def _options(**overrides):
    options = {
        "dataset": None,
        "case": None,
        "save": False,
        "target_url": None,
        "target_tag": None,
        "target_model": None,
    }
    options.update(overrides)
    return options


TARGET = Target(url="http://host.docker.internal:18071", tag="v0.0.21", model="m")


def test_resolve_target_requires_all_three_options():
    """A half-specified target could not be attributed to a cell: usage error."""
    with pytest.raises(CommandError, match="--target-url, --target-tag and --target-model"):
        Command._resolve_target(_options(target_url=TARGET.url))


def test_resolve_target_builds_target():
    """All three options give a Target; none gives None."""
    options = _options(target_url=TARGET.url, target_tag="v0.0.21", target_model="m")

    assert Command._resolve_target(options) == TARGET
    assert Command._resolve_target(_options()) is None


def test_selected_configs_skips_target_datasets_without_target():
    """`make eval` without a target still runs every in-process dataset."""
    names = [config.name for config in Command._selected_configs(_options(), None)]

    assert "multi_doc_synthesis" not in names
    assert "url_hallucination" in names


def test_selected_configs_requires_target_for_target_dataset():
    """Asking for a target dataset without a target is a usage error."""
    with pytest.raises(CommandError, match="needs a target"):
        Command._selected_configs(_options(dataset="multi_doc_synthesis"), None)


def test_selected_configs_with_target_keeps_target_dataset():
    """With a target, the target dataset is selected."""
    configs = Command._selected_configs(_options(dataset="multi_doc_synthesis"), TARGET)

    assert [config.name for config in configs] == ["multi_doc_synthesis"]


def test_save_with_dataset_allowed_only_for_target_runs():
    """Target runs save one dataset (run-vs-run diffs); in-process runs keep the old rule."""
    Command._check_save_options(_options(save=True, dataset="multi_doc_synthesis"), TARGET)

    with pytest.raises(CommandError):
        Command._check_save_options(_options(save=True, dataset="url_hallucination"), None)
    with pytest.raises(CommandError):
        Command._check_save_options(_options(save=True, case="x"), TARGET)
