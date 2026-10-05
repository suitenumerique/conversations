"""EvalConfigs for behavioral evals on ConversationAgent."""

from .base import EvalConfig
from .chat_instructions import CHAT_INSTRUCTIONS
from .faithfulness_rag import FAITHFULNESS_RAG
from .incertitude import INCERTITUDE
from .long_chat import LONG_CHAT
from .multi_doc_synthesis import MULTI_DOC_SYNTHESIS
from .project_instructions import PROJECT_INSTRUCTIONS
from .tool_selection import TOOL_SELECTION
from .url_hallucination import URL_HALLUCINATION
from .web_search import WEB_SEARCH

REGISTRY: dict[str, EvalConfig] = {
    "url_hallucination": URL_HALLUCINATION,
    "faithfulness_rag": FAITHFULNESS_RAG,
    "incertitude": INCERTITUDE,
    "tool_selection": TOOL_SELECTION,
    "multi_doc_synthesis": MULTI_DOC_SYNTHESIS,
    "chat_instructions": CHAT_INSTRUCTIONS,
    "web_search": WEB_SEARCH,
    "project_instructions": PROJECT_INSTRUCTIONS,
    "long_chat": LONG_CHAT,
}

__all__ = ["EvalConfig", "REGISTRY"]
