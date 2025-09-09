"""Build the routing agent."""

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput

from .base import _get_pydantic_agent

logger = logging.getLogger(__name__)


class UserIntent(BaseModel):
    """Model to represent the detected user intent."""

    web_search: bool = False
    attachment_summary: bool = False


def build_routing_agent(model_hrid=None, instrument=False) -> Agent[None, str] | None:
    """
    Create a Pydantic AI routing Agent instance with the configured settings.

    This agent is used to detect the user intent from the user prompt.

    Args:
        model_hrid (str | None): The HRID of the routing model to use.
            If None, the default routing model from settings will be used.
    Returns:
        Agent | None: The Pydantic AI Agent instance or None if not configured.
    Raises:
        ImproperlyConfigured: If the routing model configuration is invalid.
    """
    model_hrid = model_hrid or settings.LLM_ROUTING_MODEL_HRID

    try:
        agent = _get_pydantic_agent(
            model_hrid,
            output_type=NativeOutput([UserIntent]),
            instrument=instrument,
        )
    except ImproperlyConfigured:
        logger.info("AI routing model does not exist -> disabled")
        return None

    # Simple detection of configuration not set
    if not agent.model.model_name:
        logger.info("AI routing model configuration not set -> disabled")
        return None

    return agent
