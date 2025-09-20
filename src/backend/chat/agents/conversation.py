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

    def web_search_available(self) -> bool:
        """
        Check if web search tool is available.

        Warning, this says the tool is available, not that
        it (the tool/feature) is enabled for the current conversation.
        """
        return any(
            tool.name.startswith("web_search_")
            for toolset in self.toolsets
            for tool in toolset.tools.values()
        )
