"""Eval config: multi-document synthesis instructions, run against a target stack.

Cases attach markdown fixtures (rendered to docx) from `datasets/multi_doc_synthesis/`
and are sent over HTTP to the target given by --target-url/--target-tag/--target-model.
"""

from pathlib import Path

from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import (
    ExactBullets,
    FactRecall,
    HasMarkdownTable,
    Language,
    MaxWords,
)
from chat.evals.target.task import make_target_task_fn

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"

MULTI_DOC_SYNTHESIS = EvalConfig(
    name="multi_doc_synthesis",
    dataset_path=_DATASETS_DIR / "multi_doc_synthesis.yaml",
    make_task_fn=make_target_task_fn(_DATASETS_DIR / "multi_doc_synthesis"),
    # Types used by per-case YAML evaluators; ToolsUsed is dataset-level
    # (config.extra_evaluators) and must not be registered twice.
    dataset_evaluator_types=[
        ExactBullets,
        FactRecall,
        HasMarkdownTable,
        Language,
        MaxWords,
    ],
    requires_target=True,
)
