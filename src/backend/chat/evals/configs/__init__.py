"""EvalConfigs for behavioral evals on ConversationAgent."""

from .base import EvalConfig
from .faithfulness_rag import FAITHFULNESS_RAG
from .incertitude import INCERTITUDE
from .self_documentation import SELF_DOCUMENTATION
from .url_hallucination import URL_HALLUCINATION

REGISTRY: dict[str, EvalConfig] = {
    "url_hallucination": URL_HALLUCINATION,
    "self_documentation": SELF_DOCUMENTATION,
    "faithfulness_rag": FAITHFULNESS_RAG,
    "incertitude": INCERTITUDE,
}

__all__ = ["EvalConfig", "REGISTRY"]
