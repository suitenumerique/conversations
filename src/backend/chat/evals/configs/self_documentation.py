"""Eval config: self_documentation tool call behaviour."""

import json
from pathlib import Path

from pydantic_ai import Tool

from chat.agents.conversation import ConversationAgent
from chat.evals.configs.base import EvalConfig
from chat.tools.descriptions import SELF_DOCUMENTATION_TOOL_DESCRIPTION

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "self_documentation.yaml"


def _self_documentation() -> str:
    """Get information about the AI assistant's identity and capabilities."""
    return json.dumps(
        {
            "self_documentation": "AI assistant for productive work.",
            "runtime": {
                "model": {"hrid": "eval", "name": "Eval stub model"},
                "tools": {"web_search_feature_enabled": False},
                "attachments": {"max_size_mb": 10},
            },
        }
    )


class _SelfDocEvalAgent(ConversationAgent):
    """ConversationAgent with self_documentation tool (no DB) and its instruction."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        @self.instructions
        def self_documentation_instruction() -> str:
            return SELF_DOCUMENTATION_TOOL_DESCRIPTION

    def get_tools(self):
        return [Tool(_self_documentation, name="self_documentation", takes_ctx=False)]


SELF_DOCUMENTATION = EvalConfig(
    name="self_documentation",
    dataset_path=_DATASET_PATH,
    llm_judge_rubric=None,
    enable_tools=True,
    agent_class=_SelfDocEvalAgent,
)
