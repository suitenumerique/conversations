"""Base module for PydanticAI agents."""

import dataclasses
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import httpx
from pydantic_ai import Agent
from pydantic_ai.models import get_user_agent
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.toolsets import FunctionToolset

from chat.tools import get_pydantic_tools_by_name

logger = logging.getLogger(__name__)


def prepare_custom_model(configuration: "chat.llm_configuration.LLModel"):
    """
    Prepare a custom model instance based on the provided configuration.

    Only few providers are supported at the moment, according to our needs.
    We define custom models/providers to be able to keep specific configuration
    when needed.
    """
    # pylint: disable=import-outside-toplevel

    match configuration.provider.kind:
        case "mistral":
            import pydantic_ai.models.mistral as mistral_models  # noqa: PLC0415
            from mistralai import TextChunk as MistralTextChunk  # noqa: PLC0415
            from mistralai import ThinkChunk as MistralThinkChunk  # noqa: PLC0415
            from mistralai.types.basemodel import Unset as MistralUnset  # noqa: PLC0415
            from pydantic_ai.providers.mistral import MistralProvider  # noqa: PLC0415

            # --- Monkey patch for pydantic_ai.models.mistral._map_content ---
            # pylint: disable=protected-access

            # ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠
            # |  This workaround is fragile and only works because we are in streaming mode.  |
            # ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠ WARNING ⚠

            # The original _map_content raises exceptions for some when responses
            # contains citation/reference data, which is the case anytime we use
            # web search or other RAG tool (https://docs.mistral.ai/capabilities/citations/).
            # We make the patch idempotent using a sentinel attribute so repeated calls
            # to prepare_custom_model do not re-wrap and do not cause recursive calls.
            if not getattr(mistral_models, "__safe_map_patched__", False):
                _original_map_content = mistral_models._map_content  # noqa: SLF001

                def _safe_map_content(content):
                    """
                    A safe version of _map_content that ignores unsupported data types.

                    WARNING: this is a monkey patch and may break if the original
                    function changes in future versions of pydantic_ai.
                    Current version: pydantic_ai v1.0.18
                    """
                    text: str | None = None
                    thinking: list[str] = []

                    if isinstance(content, MistralUnset) or not content:
                        return None, []

                    if isinstance(content, list):
                        for chunk in content:
                            if isinstance(chunk, MistralTextChunk):
                                text = (text or "") + chunk.text
                            elif isinstance(chunk, MistralThinkChunk):
                                for thought in chunk.thinking:
                                    if thought.type == "text":  # pragma: no branch
                                        thinking.append(thought.text)
                            else:
                                logger.info(  # pragma: no cover
                                    "Other data types like (Image, Reference) are not yet "
                                    "supported,  got %s",
                                    type(chunk),
                                )
                    elif isinstance(content, str):
                        text = content

                    # Note: Check len to handle potential mismatch between function calls and
                    # responses from the API.
                    # (`msg: not the same number of function class and responses`)
                    if text == "":  # pragma: no cover
                        text = None

                    return text, thinking

                # Replace the original module-level function
                mistral_models._map_content = _safe_map_content  # noqa: SLF001
                mistral_models.__safe_map_patched__ = True
            # pylint: enable=protected-access
            # --- End monkey patch ---

            return mistral_models.MistralModel(
                model_name=configuration.model_name,
                profile=(
                    ModelProfile(**configuration.profile.dict(exclude_unset=True))
                    if configuration.profile
                    else None
                ),
                provider=MistralProvider(
                    api_key=configuration.provider.api_key,
                    base_url=configuration.provider.base_url,
                    # Disable the use of cached client
                    http_client=httpx.AsyncClient(
                        timeout=httpx.Timeout(timeout=600, connect=5),
                        headers={"User-Agent": get_user_agent()},
                    ),
                ),
            )
        case "openai":
            from pydantic_ai.models.openai import OpenAIChatModel  # noqa: PLC0415
            from pydantic_ai.profiles.openai import OpenAIModelProfile  # noqa: PLC0415
            from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

            if configuration.profile and (
                _config_profile := configuration.profile.dict(exclude_unset=True)
            ):
                # set some defaults if not provided, see openai_model_profile which
                # defines them for known models
                _model_profile_params = {
                    "supports_json_schema_output": True,
                    "supports_json_object_output": True,
                }
                _model_profile_params.update(_config_profile)
                profile = OpenAIModelProfile(**_model_profile_params)
            else:
                profile = None

            return OpenAIChatModel(
                model_name=configuration.model_name,
                profile=profile,
                provider=OpenAIProvider(
                    base_url=configuration.provider.base_url,
                    api_key=configuration.provider.api_key,
                ),
            )
        case _:
            raise ImproperlyConfigured(
                f"Unsupported provider kind '{configuration.provider.kind}' for custom model."
            )


@dataclasses.dataclass(init=False)
class BaseAgent(Agent):
    """
    Base class for PydanticAI agents.

    This class initializes the agent with model from configuration.
    """

    def __init__(self, *, model_hrid, **kwargs):
        """Initialize the agent with model configuration from settings."""
        _ignored_kwargs = {"model", "system_prompt", "tools", "toolsets"}
        if set(kwargs).intersection(_ignored_kwargs):
            raise ValueError(f"{_ignored_kwargs} arguments must not be provided.")

        try:
            self.configuration = settings.LLM_CONFIGURATIONS[model_hrid]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"LLM model configuration '{model_hrid}' not found."
            ) from exc

        if self.configuration.is_custom:
            _model_instance = prepare_custom_model(self.configuration)
        else:
            # In this case, we rely on PydanticAI's built-in model registry
            # and configuration: check pydantic_ai.models.KnownModelName
            # and pydantic_ai.models.infer_model()
            _model_instance = self.configuration.model_name

        _system_prompt = self.configuration.system_prompt
        _base_toolset = (
            [
                FunctionToolset(
                    tools=[
                        get_pydantic_tools_by_name(tool_name)
                        for tool_name in self.configuration.tools
                    ]
                )
            ]
            if self.configuration.tools
            else None
        )

        _tools = [get_pydantic_tools_by_name(tool_name) for tool_name in self.configuration.tools]

        super().__init__(
            model=_model_instance, system_prompt=_system_prompt, tools=_tools, **kwargs
        )
