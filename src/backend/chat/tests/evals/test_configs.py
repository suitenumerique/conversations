"""Tests for eval config loading from the dataset YAML ``config`` block."""

import yaml
from pydantic_evals import Dataset

from chat.evals import EvalInputs, EvalMetadata
from chat.evals.configs import REGISTRY
from chat.evals.configs.base import split_dataset_file


def test_split_dataset_file_strips_config_block():
    """The config block is extracted and removed from the pydantic_evals data."""
    config, data = split_dataset_file(REGISTRY["url_hallucination"].dataset_path)

    assert "llm_judge_rubric" in config
    assert "config" not in data
    assert data["cases"]


def test_rubrics_and_evaluators_resolved_from_yaml():
    """EvalConfig lazily resolves rubric and evaluator dotted paths from the YAML."""
    url = REGISTRY["url_hallucination"]
    assert "hallucinated URLs" in url.llm_judge_rubric
    assert [type(e).__name__ for e in url.extra_evaluators] == ["UrlRegexEvaluator"]

    faithfulness = REGISTRY["faithfulness_rag"]
    assert "FAITHFUL" in faithfulness.llm_judge_rubric
    assert [e.evaluation_name for e in faithfulness.extra_evaluators] == [
        "ran_document_search_rag",
        "did_not_call_web_search",
    ]

    assert "PERSONAL SITUATION" in REGISTRY["incertitude"].llm_judge_rubric

    tool_selection = REGISTRY["tool_selection"]
    assert tool_selection.llm_judge_rubric is None
    assert not tool_selection.extra_evaluators


def test_all_datasets_parse_after_config_strip():
    """Every registered dataset must load as a pydantic_evals Dataset (run_evals path)."""
    for name, config in REGISTRY.items():
        _, data = split_dataset_file(config.dataset_path)
        custom_evaluator_types = [
            *config.dataset_evaluator_types,
            *[type(e) for e in config.extra_evaluators],
        ]
        dataset = Dataset[EvalInputs, str, EvalMetadata].from_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            fmt="yaml",
            custom_evaluator_types=custom_evaluator_types,
            default_name=name,
        )
        assert dataset.cases, f"dataset '{name}' has no cases"
