"""Tests for loading eval datasets declared as plain pydantic_evals YAML."""

from pydantic_evals.evaluators import LLMJudge

from chat.evals.configs import REGISTRY


def _dataset_evaluators(name: str) -> list:
    return REGISTRY[name].load_dataset().evaluators


def test_all_datasets_load():
    """Every registered dataset loads as a pydantic_evals Dataset (run_evals path)."""
    for name, config in REGISTRY.items():
        assert config.load_dataset().cases, f"dataset '{name}' has no cases"


def test_judged_datasets_declare_their_rubric():
    """Dataset-level LLMJudge rubrics are read from the YAML evaluators list."""
    rubrics = {
        name: [e.rubric for e in _dataset_evaluators(name) if isinstance(e, LLMJudge)]
        for name in ("url_hallucination", "faithfulness_rag", "incertitude")
    }

    assert "hallucinated URLs" in rubrics["url_hallucination"][0]
    assert "FAITHFUL" in rubrics["faithfulness_rag"][0]
    assert "PERSONAL SITUATION" in rubrics["incertitude"][0]


def test_dataset_level_evaluators_resolved_from_yaml():
    """Custom and span evaluators keep the names saved runs are compared on."""
    assert [type(e).__name__ for e in _dataset_evaluators("url_hallucination")] == [
        "UrlRegexEvaluator",
        "LLMJudge",
    ]
    assert [e.evaluation_name for e in _dataset_evaluators("faithfulness_rag")[:2]] == [
        "ran_document_search_rag",
        "did_not_call_web_search",
    ]
    assert not _dataset_evaluators("tool_selection")
