"""Build the main conversation agent."""

import logging

from django.utils import formats, timezone

from pydantic_ai import Agent

from core.enums import get_language_name

from .base import _get_pydantic_agent

logger = logging.getLogger(__name__)


def build_conversation_agent(
    *, mcp_servers, model_hrid, language=None, instrument=False
) -> Agent[None, str]:
    """Create a Pydantic AI Agent instance with the configured settings."""

    agent = _get_pydantic_agent(model_hrid, mcp_servers, instrument=instrument)

    @agent.system_prompt
    def add_the_date() -> str:
        """
        Dynamic system prompt function to add the current date.

        Warning: this will always use the date in the server timezone,
        not the user's timezone...
        """
        _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)
        return f"Today is {_formatted_date}."

    @agent.system_prompt
    def enforce_response_language() -> str:
        """Dynamic system prompt function to set the expected language to use."""
        return f"Answer in {get_language_name(language).lower()}." if language else ""

    return agent
