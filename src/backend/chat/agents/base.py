"""Base module for PydanticAI agents."""

import dataclasses

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from chat.tools import get_pydantic_tools_by_name


@dataclasses.dataclass(init=False)
class BaseAgent(Agent):
    """
    Base class for PydanticAI agents.

    This class initializes the agent with model from configuration.
    """

    def __init__(self, *, model_hrid, **kwargs):
        """Initialize the agent with model configuration from settings."""
        _ignored_kwargs = {"model", "system_prompt", "tools"}
        if set(kwargs).intersection(_ignored_kwargs):
            raise ValueError(f"{_ignored_kwargs} arguments must not be provided.")

        try:
            self.configuration = settings.LLM_CONFIGURATIONS[model_hrid]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"LLM model configuration '{model_hrid}' not found."
            ) from exc

        _model_instance = OpenAIChatModel(
            model_name=self.configuration.model_name,
            profile=(
                OpenAIModelProfile(**self.configuration.profile.dict(exclude_unset=True))
                if self.configuration.profile
                else None
            ),
            provider=OpenAIProvider(
                base_url=self.configuration.provider.base_url,
                api_key=self.configuration.provider.api_key,
            )
            if self.configuration.provider
            else None,
        )
        _system_prompt = self.configuration.system_prompt
        _tools = [get_pydantic_tools_by_name(tool_name) for tool_name in self.configuration.tools]

        super().__init__(
            model=_model_instance, system_prompt=_system_prompt, tools=_tools, **kwargs
        )
