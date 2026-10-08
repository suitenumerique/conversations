"""Eval configs for datasets run like production conversations (see ``chat.evals.in_process``).

Every case's fixture documents live in ``datasets/multi_doc_synthesis/``.
"""

from pathlib import Path

from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import CUSTOM_EVALUATOR_TYPES
from chat.evals.in_process import make_in_process_task_fn
from chat.evals.target.task import make_target_task_fn

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
DOCUMENTS_DIR = _DATASETS_DIR / "multi_doc_synthesis"


def _conversation_config(
    name: str, *, smart_web_search: bool = False, over_http: bool = True
) -> EvalConfig:
    return EvalConfig(
        name=name,
        dataset_path=_DATASETS_DIR / f"{name}.yaml",
        make_task_fn=make_in_process_task_fn(DOCUMENTS_DIR, smart_web_search=smart_web_search),
        http_task=(
            make_target_task_fn(DOCUMENTS_DIR, smart_web_search=smart_web_search)
            if over_http
            else None
        ),
        dataset_evaluator_types=list(CUSTOM_EVALUATOR_TYPES),
    )


CHAT_INSTRUCTIONS = _conversation_config("chat_instructions")
WEB_SEARCH = _conversation_config("web_search", smart_web_search=True)
MULTI_DOC_SYNTHESIS = _conversation_config("multi_doc_synthesis")
PROJECT_INSTRUCTIONS = _conversation_config("project_instructions")
# A frozen post-summary state cannot be set up through the API.
LONG_CHAT = _conversation_config("long_chat", over_http=False)
KIWI = _conversation_config("kiwi")
CLAUDE_STYLE = _conversation_config("claude_style")
