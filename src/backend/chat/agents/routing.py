"""Build the routing agent."""

import dataclasses
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from pydantic import BaseModel
from pydantic_ai import NativeOutput

from .base import BaseAgent

logger = logging.getLogger(__name__)


class UserIntent(BaseModel):
    """Model to represent the detected user intent."""

    web_search: bool = False
    attachment_summary: bool = False


@dataclasses.dataclass(init=False)
class RoutingAgent(BaseAgent):
    """
    Create a Pydantic AI routing Agent instance with the configured settings.

    This agent is used to detect the user intent from the user prompt.
    """

    def __init__(self, **kwargs):
        """Initialize the routing agent with the configured model."""
        try:
            super().__init__(
                model_hrid=settings.LLM_ROUTING_MODEL_HRID,
                output_type=NativeOutput([UserIntent]),
                **kwargs,
            )
        except ImproperlyConfigured:
            logger.info("AI routing model does not exist -> disabled")
            raise

        if not self.model.model_name:
            logger.info("AI routing model configuration not set -> disabled")
            raise ImproperlyConfigured("AI routing model configuration not set -> disabled")

        if self.configuration.tools:
            logger.warning("Routing agent should not have tools configured.")
