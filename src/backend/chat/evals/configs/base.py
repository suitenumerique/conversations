"""Base EvalConfig and related classes for behavioral evals on ConversationAgent."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_evals.evaluators import Evaluator

from chat.agents.conversation import ConversationAgent

# A task factory: given the model hrid, return the async task function the eval
# runner calls with each case's inputs and that returns the agent's text output.
TaskFactory = Callable[[str], Callable[..., Awaitable[str]]]


@dataclass
class EvalConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for a behavioral eval on ConversationAgent."""

    name: str
    dataset_path: Path
    llm_judge_rubric: str | None  # None = skip LLMJudge entirely
    extra_evaluators: list[Evaluator] = field(default_factory=list)
    enable_tools: bool = False
    # Custom agent class to instantiate instead of the default (_EvalAgent or ConversationAgent).
    agent_class: type[ConversationAgent] | None = None
    # Custom task factory. When set, it fully replaces the default run logic
    # (agent_class / enable_tools / tool_output prompt injection are ignored).
    # Use it when the eval needs control over how the agent is invoked, e.g. to
    # stage per-case context for a stub tool so the model actually calls it.
    make_task_fn: TaskFactory | None = None
    # Evaluator types referenced only in the dataset YAML (per-case), not at dataset level.
    dataset_evaluator_types: list[type] = field(default_factory=list)
