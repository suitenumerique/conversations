"""Eval config: web search behaviour (smart search opted in), run against a target stack."""

from pathlib import Path

from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import (
    ExactBullets,
    Language,
    MaxWords,
    SourcesCount,
    ToolCalled,
    ToolNotCalled,
    UrlCount,
    UrlRegexEvaluator,
)
from chat.evals.target.task import make_target_task_fn

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"

WEB_SEARCH = EvalConfig(
    name="web_search",
    dataset_path=_DATASETS_DIR / "web_search.yaml",
    make_task_fn=make_target_task_fn(_DATASETS_DIR / "multi_doc_synthesis", smart_web_search=True),
    dataset_evaluator_types=[
        ExactBullets,
        Language,
        MaxWords,
        SourcesCount,
        ToolCalled,
        ToolNotCalled,
        UrlCount,
        UrlRegexEvaluator,
    ],
    requires_target=True,
)
