"""Eval config: instruction following in chats without documents, run against a target stack."""

from pathlib import Path

from chat.evals.configs.base import EvalConfig
from chat.evals.target.task import make_target_task_fn

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"

CHAT_INSTRUCTIONS = EvalConfig(
    name="chat_instructions",
    dataset_path=_DATASETS_DIR / "chat_instructions.yaml",
    make_task_fn=make_target_task_fn(_DATASETS_DIR / "multi_doc_synthesis"),
    requires_target=True,
)
