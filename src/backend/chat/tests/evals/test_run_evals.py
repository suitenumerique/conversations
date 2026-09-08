"""Tests for the run_evals management command helpers."""
# pylint: disable=protected-access

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
