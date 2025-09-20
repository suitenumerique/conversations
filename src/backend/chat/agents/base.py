"""Base module for PydanticAI agents."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from chat.tools import get_pydantic_tools_by_name


def _get_pydantic_agent(model_hrid, mcp_servers=None, **kwargs) -> Agent:
    """Get the PydanticAI Agent instance with the configured settings."""
    try:
        _model = settings.LLM_CONFIGURATIONS[model_hrid]
    except KeyError as exc:
        raise ImproperlyConfigured(f"LLM model configuration '{model_hrid}' not found.") from exc

    _model_instance = OpenAIChatModel(
        model_name=_model.model_name,
        provider=OpenAIProvider(
            base_url=_model.provider.base_url,
            api_key=_model.provider.api_key,
        )
        if _model.provider
        else None,
    )
    _system_prompt = _model.system_prompt
    _tools = [get_pydantic_tools_by_name(tool_name) for tool_name in _model.tools]

    return Agent(
        model=_model_instance,
        system_prompt=_system_prompt,
        mcp_servers=mcp_servers or [],
        tools=_tools,
        **kwargs,
    )
