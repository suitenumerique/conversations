"""Base EvalConfig and related classes for behavioral evals on ConversationAgent."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic_evals import Dataset

from chat.agents.conversation import ConversationAgent
from chat.evals import EvalInputs, EvalMetadata
from chat.evals.evaluators import CUSTOM_EVALUATOR_TYPES

# A task factory: given the model hrid, return the async task function the eval
# runner calls with each case's inputs and that returns the agent's text output.
TaskFactory = Callable[[str], Callable[..., Awaitable[str]]]


@dataclass
class EvalConfig:
    """Configuration for a behavioral eval on ConversationAgent.

    The dataset YAML is a plain pydantic_evals file (cases and evaluators,
    LLM judge included); this class only wires the executable parts (task
    factory, agent class).
    """

    name: str
    dataset_path: Path
    enable_tools: bool = False
    # Custom agent class to instantiate instead of the default (_EvalAgent or ConversationAgent).
    agent_class: type[ConversationAgent] | None = None
    # Custom task factory. When set, it fully replaces the default run logic
    # (agent_class / enable_tools / tool_output prompt injection are ignored).
    # Use it when the eval needs control over how the agent is invoked, e.g. to
    # stage per-case context for a stub tool so the model actually calls it.
    make_task_fn: TaskFactory | None = None
    # True for datasets that drive a target stack over HTTP (--target-* options).
    requires_target: bool = False

    def load_dataset(self) -> Dataset[EvalInputs, str, EvalMetadata]:
        """Parse the dataset YAML with every custom evaluator type registered."""
        return Dataset[EvalInputs, str, EvalMetadata].from_file(
            self.dataset_path, custom_evaluator_types=CUSTOM_EVALUATOR_TYPES
        )
