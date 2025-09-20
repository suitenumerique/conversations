"""Build the main conversation agent."""

import dataclasses
import logging

from django.utils import formats, timezone

from core.enums import get_language_name

from .base import BaseAgent

logger = logging.getLogger(__name__)


@dataclasses.dataclass(init=False)
class ConversationAgent(BaseAgent):
    """Conversation agent with custom behavior."""

    def __init__(self, *, language=None, **kwargs):
        """Initialize the conversation agent."""
        super().__init__(**kwargs)

        @self.system_prompt
        def add_the_date() -> str:
            """
            Dynamic system prompt function to add the current date.

            Warning: this will always use the date in the server timezone,
            not the user's timezone...
            """
            _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)
            return f"Today is {_formatted_date}."

        @self.system_prompt
        def enforce_response_language() -> str:
            """Dynamic system prompt function to set the expected language to use."""
            return f"Answer in {get_language_name(language).lower()}." if language else ""

        @self.system_prompt
        def rag_instructions() -> str:
            """Dynamic system prompt function to add RAG instructions if any."""
            return """
When a user requests a summary or has a question that requires content from a document, you should:
Call the summarize tool
If the user wants a summary of a document, invoke summarize without asking the user for the document itself.
The tool will handle any necessary extraction and summarization based on the internal context.
Call the document_search_albert_rag tool
If the user wants specific information from a document, invoke document_search_albert_rag with an appropriate query string.
Do not ask the user for the document; rely on the tool to locate and return relevant passages.
    """



