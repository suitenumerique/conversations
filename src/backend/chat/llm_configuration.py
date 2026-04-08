"""Module for managing LLM configurations from a JSON configuration file."""

import logging
import os
from functools import lru_cache
from typing import Annotated, Any, Literal, Optional, Self, Sequence

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    ImportString,
    field_validator,
    model_validator,
)
from pydantic_ai.profiles import JsonSchemaTransformer

logger = logging.getLogger(__name__)

# Legacy tool names that were moved to the `web_search` setting.
# Kept here for backward compatibility: old configs that still list them
# under `tools` won't break - the values are stripped and a warning is logged
# so admins know to update their configuration.
LEGACY_TOOL_NAMES = frozenset(
    {
        "web_search_brave",
        "web_search_brave_with_document_backend",
        "web_search_tavily",
        "web_search_albert_rag",
    }
)


def _get_setting_or_env_or_value(value: str) -> Any:
    """Get the value from environment variable, Django settings, or return the value as is."""
    from django.conf import settings  # pylint: disable=import-outside-toplevel # noqa: PLC0415

    if value.startswith("environ."):
        env_var = value.split("environ.")[1]
        new_value = os.environ.get(env_var, None)
        if new_value is None:
            raise ValueError(f"Environment variable '{env_var}' not set.")
        return new_value

    if value.startswith("settings."):
        setting_var = value.split("settings.")[1]
        new_value = getattr(settings, setting_var, None)
        if new_value is None:
            raise ValueError(f"Django setting '{setting_var}' not set.")
        return new_value

    return value


SettingEnvValue = Annotated[
    str,
    AfterValidator(_get_setting_or_env_or_value),
]

LongStringAsListValue = Annotated[
    str,
    BeforeValidator(lambda v: "".join(v) if isinstance(v, list) else v),
]


class LLMProvider(BaseModel):
    """Model representing a provider of Large Language Models (LLMs)."""

    hrid: str
    base_url: SettingEnvValue
    api_key: SettingEnvValue
    kind: Literal["openai", "mistral"] = "openai"
    co2_handling: Optional[Literal["albert"]] = None  # for now, only Albert has CO2 handling,
    # but this leaves room for other providers to implement it in the future


class LLMProfile(BaseModel):
    """Based on pydantic_ai.profiles.ModelProfile to allow customization."""

    supports_tools: bool | None = None
    supports_json_schema_output: bool | None = None
    supports_json_object_output: bool | None = None
    default_structured_output_mode: str | None = None
    prompted_output_template: str | None = None
    json_schema_transformer: ImportString | None = Field(default=None, validate_default=True)
    thinking_tags: tuple[str, str] | None = None
    ignore_streamed_leading_whitespace: bool | None = None

    # openai specific settings: should find a way to auto declare these
    # based on OpenAIModelProfile.
    openai_supports_strict_tool_definition: bool | None = None
    openai_unsupported_model_settings: Sequence[str] | None = None
    openai_supports_tool_choice_required: bool | None = None
    openai_system_prompt_role: str | None = None
    openai_chat_supports_web_search: bool | None = None
    openai_supports_encrypted_reasoning_content: bool | None = None

    @field_validator("json_schema_transformer", mode="after")
    @classmethod
    def validate_json_schema_transformer(
        cls, value: JsonSchemaTransformer | None
    ) -> Optional[JsonSchemaTransformer]:
        """Convert the tools if it's a setting or environment variable."""
        if not value:
            return None

        if issubclass(value, JsonSchemaTransformer):
            return value

        raise ValueError(f"Invalid JSON Schema Transformer '{value}'")


class LLMSettings(BaseModel):
    """Based on pydantic_ai.settings.ModelSettings to allow customization."""

    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    timeout: float | None = None
    parallel_tool_calls: bool | None = None
    seed: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    logit_bias: dict[str, int] | None = None
    stop_sequences: list[str] | None = None
    extra_headers: dict[str, str] | None = None
    extra_body: dict[str, str] | None = None


class LLModel(BaseModel):
    """Model representing a Large Language Model (LLM)."""

    hrid: str
    model_name: SettingEnvValue
    human_readable_name: str
    profile: LLMProfile | None = None
    provider_name: str | None = None
    provider: LLMProvider | None = None
    settings: LLMSettings | None = None
    is_active: bool
    icon: LongStringAsListValue | None = None
    supports_streaming: bool | None = None
    system_prompt: SettingEnvValue
    tools: list[str]
    web_search: SettingEnvValue | None = None
    concatenate_instruction_messages: bool | None = None
    max_token_context: int | None = None

    @field_validator("tools", mode="before")
    @classmethod
    def validate_tools(cls, value: list[str] | str) -> list[str]:
        """Convert the tools if it's a setting or environment variable."""
        if isinstance(value, str):
            value = _get_setting_or_env_or_value(value)

        # Strip legacy tool names that are now handled by `web_search`
        legacy_found = LEGACY_TOOL_NAMES.intersection(value)
        if legacy_found:
            logger.warning(
                "Ignoring legacy tool(s) %s in model configuration. "
                "Use the 'web_search' setting instead.",
                ", ".join(sorted(legacy_found)),
            )
            value = [t for t in value if t not in LEGACY_TOOL_NAMES]

        return value

    @field_validator("web_search", mode="before")
    @classmethod
    def validate_web_search(cls, value: str | None) -> str | None:
        """Convert web_search path if it's a setting or environment variable."""
        if isinstance(value, str):
            return _get_setting_or_env_or_value(value)
        return value

    @field_validator("max_token_context", mode="before")
    @classmethod
    def validate_max_token_context(cls, value: int | str | None) -> int | None:
        """Accept integer-like values from JSON for model context size."""
        if value is None or value == "":
            return None
        if isinstance(value, int):
            parsed_value = value
        elif isinstance(value, str):
            parsed_value = int(value)
        else:
            raise ValueError("max_token_context must be an integer value.")

        if parsed_value <= 0:
            raise ValueError("max_token_context must be a positive integer")

        return parsed_value

    @model_validator(mode="after")
    def check_provider_or_provider_name(self) -> Self:
        """
        Do some validation regarding provider and provider_name:
        - Either `provider_name` or `provider` must be set, but not both.
        - If neither is set, `model_name` must be in the format '<provider>:<model>'.
        """
        if bool(self.provider_name) and bool(self.provider):
            raise ValueError("Either 'provider_name' or 'provider' must be set, but not both.")
        if not self.provider_name and not self.provider and len(self.model_name.split(":")) != 2:
            raise ValueError(
                "Either 'provider_name' or 'provider' must be set, "
                "unless model_name starts with '<provider>:'."
            )
        return self

    @property
    def is_custom(self) -> bool:
        """Return True if the model is a custom model (i.e., defines a provider)."""
        return self.provider is not None


class LLMConfiguration(BaseModel):
    """Model representing the entire LLM configuration."""

    models: list[LLModel]
    providers: list[LLMProvider]

    @model_validator(mode="after")
    def fill_providers(self) -> Self:
        """Fill in the `provider` field of each model based on `provider_name`."""
        provider_map = {provider.hrid: provider for provider in self.providers}
        for model in self.models:
            if model.provider_name:
                try:
                    model.provider = provider_map[model.provider_name]
                except KeyError as exc:
                    raise ValueError(
                        f"Provider '{model.provider_name}' not found "
                        f"for model '{model.model_name}'."
                    ) from exc
        return self


def _read_llm_configuration(llm_configuration_file_path) -> LLMConfiguration:
    """Read the LLM configuration from a JSON file and return an LLMConfiguration instance."""
    with open(llm_configuration_file_path, "rb") as f:
        data = f.read().decode("utf-8")
    return LLMConfiguration.model_validate_json(data)


def load_llm_configuration(llm_configuration_file_path) -> dict[str, LLModel]:
    """Load the LLM configuration and return a mapping of model HRIDs to LLModel instances."""
    configuration = _read_llm_configuration(llm_configuration_file_path)
    model_map = {model.hrid: model for model in configuration.models}
    return model_map


@lru_cache(maxsize=1)
def cached_load_llm_configuration(llm_configuration_file_path) -> dict[str, LLModel]:
    """Load the LLM configuration with caching to avoid redundant loading."""
    return load_llm_configuration(llm_configuration_file_path)
