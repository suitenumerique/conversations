"""Base EvalConfig and related classes for behavioral evals on ConversationAgent."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from django.utils.module_loading import import_string

import yaml
from pydantic_evals.evaluators import Evaluator

from chat.agents.conversation import ConversationAgent

# A task factory: given the model hrid, return the async task function the eval
# runner calls with each case's inputs and that returns the agent's text output.
TaskFactory = Callable[[str], Callable[..., Awaitable[str]]]


def split_dataset_file(dataset_path: Path) -> tuple[dict, dict]:
    """Split a dataset YAML into its ``config`` block and the pydantic_evals data.

    Dataset files carry an optional top-level ``config`` mapping (LLM judge
    rubric, dotted paths to extra evaluators). pydantic_evals forbids unknown
    keys, so the block must be stripped before the rest is parsed as a Dataset.
    """
    data = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
    return data.pop("config", None) or {}, data


@dataclass
class EvalConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for a behavioral eval on ConversationAgent.

    Declarative parts (LLM judge rubric, extra evaluators) live in the dataset
    YAML ``config`` block and are resolved lazily; this class only wires the
    executable parts (task factory, agent class).
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
    # Evaluator types referenced only in the dataset YAML (per-case), not at dataset level.
    dataset_evaluator_types: list[type] = field(default_factory=list)

    @cached_property
    def _yaml_config(self) -> dict:
        return split_dataset_file(self.dataset_path)[0]

    @property
    def llm_judge_rubric(self) -> str | None:
        """LLM judge rubric from the dataset YAML (None = skip LLMJudge entirely)."""
        return self._yaml_config.get("llm_judge_rubric")

    @cached_property
    def extra_evaluators(self) -> list[Evaluator]:
        """Dataset-level evaluators from the YAML ``config`` block.

        Each entry is a dotted path to either an Evaluator instance (used
        as-is) or an Evaluator class (instantiated without arguments).
        """
        evaluators = []
        for dotted_path in self._yaml_config.get("extra_evaluators", []):
            resolved = import_string(dotted_path)
            evaluators.append(resolved() if isinstance(resolved, type) else resolved)
        return evaluators
