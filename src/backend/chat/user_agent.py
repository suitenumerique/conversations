"""The User-Agent Conversations sends on its outgoing LLM and MCP calls."""

from django.conf import settings


def get_user_agent() -> str:
    """Name Conversations on outgoing calls, so the services it calls can recognise it.

    `OUTGOING_USER_AGENT` replaces the default, `conversations/<release>`.
    """
    return settings.OUTGOING_USER_AGENT or f"conversations/{settings.RELEASE}"
