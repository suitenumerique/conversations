"""Eval config: web search behaviour (smart search opted in), run against a target stack."""

from pathlib import Path

from chat.evals.configs.base import EvalConfig
from chat.evals.target.task import make_target_task_fn

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"

WEB_SEARCH = EvalConfig(
    name="web_search",
    dataset_path=_DATASETS_DIR / "web_search.yaml",
    make_task_fn=make_target_task_fn(_DATASETS_DIR / "multi_doc_synthesis", smart_web_search=True),
    requires_target=True,
)
