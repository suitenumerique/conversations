"""Base EvalConfig and related classes for behavioral evals on ConversationAgent."""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic_evals.evaluators import Evaluator

from chat.agents.conversation import ConversationAgent


@dataclass
class EvalConfig:
    """Configuration for a behavioral eval on ConversationAgent."""

    name: str
    dataset_path: Path
    llm_judge_rubric: str | None  # None = skip LLMJudge entirely
    extra_evaluators: list[Evaluator] = field(default_factory=list)
    enable_tools: bool = False
    # Custom agent class to instantiate instead of the default (_EvalAgent or ConversationAgent).
    agent_class: type[ConversationAgent] | None = None
