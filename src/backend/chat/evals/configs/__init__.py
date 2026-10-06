"""EvalConfigs for behavioral evals on ConversationAgent."""

from .base import EvalConfig
from .datagouv_selection import DATAGOUV_SELECTION
from .faithfulness_rag import FAITHFULNESS_RAG
from .incertitude import INCERTITUDE
from .tool_selection import TOOL_SELECTION
from .url_hallucination import URL_HALLUCINATION

REGISTRY: dict[str, EvalConfig] = {
    "url_hallucination": URL_HALLUCINATION,
    "faithfulness_rag": FAITHFULNESS_RAG,
    "incertitude": INCERTITUDE,
    "tool_selection": TOOL_SELECTION,
    "datagouv_selection": DATAGOUV_SELECTION,
}

__all__ = ["EvalConfig", "REGISTRY"]
