"""Eval config: self_documentation tool call behaviour."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic_evals.evaluators import HasMatchingSpan

from chat.evals import EvalInputs
from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import HasNoMatchingSpan
from chat.evals.production_agent import build_production_agent_service, production_agent_deps

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "self_documentation.yaml"


def make_self_documentation_task_fn(model_hrid: str):
    """Build the task function using production agent wiring (stub DB only)."""
    service = build_production_agent_service(model_hrid)
    agent = service.conversation_agent
    deps = production_agent_deps(service)

    async def run_agent(inputs: EvalInputs) -> str:
        with patch(
            "chat.tools.self_documentation.load_db_self_documentation",
            new_callable=AsyncMock,
            return_value="",
        ):
            return (await agent.run(inputs.user_message, deps=deps)).output

    return run_agent


SELF_DOCUMENTATION = EvalConfig(
    name="self_documentation",
    dataset_path=_DATASET_PATH,
    llm_judge_rubric=None,
    dataset_evaluator_types=[HasMatchingSpan, HasNoMatchingSpan],
    make_task_fn=make_self_documentation_task_fn,
)
