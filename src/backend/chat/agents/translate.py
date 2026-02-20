"""Build the translation agent."""

import dataclasses
import logging

from django.conf import settings

from .base import BaseAgent

logger = logging.getLogger(__name__)


@dataclasses.dataclass(init=False)
class TranslationAgent(BaseAgent):
    """Create a Pydantic AI translation Agent instance with the configured settings"""

    def __init__(self, **kwargs):
        """Initialize the agent with the configured model."""
        super().__init__(
            model_hrid=settings.LLM_SUMMARIZATION_MODEL_HRID,
            output_type=str,
            **kwargs,
        )
