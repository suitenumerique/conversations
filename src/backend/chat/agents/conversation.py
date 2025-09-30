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

    def get_web_search_tool_name(self) -> str | None:
        """
        Get the name of the web search tool if available.

        If several are available, return the first one found.

        Warning, this says the tool is available, not that
        it (the tool/feature) is enabled for the current conversation.
        """
        for toolset in self.toolsets:
            for tool in toolset.tools.values():
                if tool.name.startswith("web_search_"):
                    return tool.name
        return None
