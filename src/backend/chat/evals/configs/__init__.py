"""EvalConfigs for behavioral evals on ConversationAgent."""

from .base import EvalConfig
from .self_documentation import SELF_DOCUMENTATION
from .url_hallucination import URL_HALLUCINATION

REGISTRY: dict[str, EvalConfig] = {
    "url_hallucination": URL_HALLUCINATION,
    "self_documentation": SELF_DOCUMENTATION,
}

__all__ = ["EvalConfig", "REGISTRY"]
