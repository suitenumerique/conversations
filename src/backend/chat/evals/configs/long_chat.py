"""Eval config: rules and facts surviving history summarization, run against a target stack.

Turns paste long fixture reports ({{paste:long-cr-0N}}) so the history crosses the
summarization budget before the scored turn.
"""

from pathlib import Path

from chat.evals.configs.base import EvalConfig
from chat.evals.target.task import make_target_task_fn

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"

LONG_CHAT = EvalConfig(
    name="long_chat",
    dataset_path=_DATASETS_DIR / "long_chat.yaml",
    make_task_fn=make_target_task_fn(_DATASETS_DIR / "multi_doc_synthesis"),
    requires_target=True,
)
