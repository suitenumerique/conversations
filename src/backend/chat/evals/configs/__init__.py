"""EvalConfigs for behavioral evals on ConversationAgent."""

from .base import EvalConfig
from .conversation import (
    CHAT_INSTRUCTIONS,
    CLAUDE_STYLE,
    KIWI,
    LONG_CHAT,
    MULTI_DOC_SYNTHESIS,
    PROJECT_INSTRUCTIONS,
    WEB_SEARCH,
)
from .faithfulness_rag import FAITHFULNESS_RAG
from .incertitude import INCERTITUDE
from .tool_selection import TOOL_SELECTION
from .url_hallucination import URL_HALLUCINATION

REGISTRY: dict[str, EvalConfig] = {
    "url_hallucination": URL_HALLUCINATION,
    "faithfulness_rag": FAITHFULNESS_RAG,
    "incertitude": INCERTITUDE,
    "tool_selection": TOOL_SELECTION,
    "chat_instructions": CHAT_INSTRUCTIONS,
    "web_search": WEB_SEARCH,
    "multi_doc_synthesis": MULTI_DOC_SYNTHESIS,
    "project_instructions": PROJECT_INSTRUCTIONS,
    "long_chat": LONG_CHAT,
    "kiwi": KIWI,
    "claude_style": CLAUDE_STYLE,
}

__all__ = ["EvalConfig", "REGISTRY"]
