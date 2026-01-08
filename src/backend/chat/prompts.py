"""Runtime access helpers for synced prompts."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from chat.models import Prompt


def get_prompt(name: str) -> str:
    """
    Return the content of a prompt by name.

    Fallback strategy:
    - if the prompt is not found in DB, return the legacy setting-based prompt
      for known names (e.g. assistant_system).
    """

    try:
        prompt = Prompt.objects.get(name=name)
        return prompt.content
    except ObjectDoesNotExist:
        # Fallbacks to keep backward compatibility and avoid hard failures.
        if name == "assistant_system":
            return settings.AI_AGENT_INSTRUCTIONS
        if name == "summarizer":
            return settings.SUMMARIZATION_SYSTEM_PROMPT

        raise


