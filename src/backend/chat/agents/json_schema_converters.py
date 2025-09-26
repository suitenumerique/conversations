"""Custom JSON schema transformers."""

import logging
from dataclasses import dataclass

from pydantic_ai.profiles._json_schema import JsonSchema
from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer

logger = logging.getLogger(__name__)


@dataclass
class MistralVllmJsonSchemaTransformer(OpenAIJsonSchemaTransformer):
    """
    Custom JsonSchema transformer for Mistral models deployed using vLLM.

    vLLM's OpenAI-compatible endpoint does not support the `function_strict` setting.
    See discussion:
    https://discuss.vllm.ai/t/the-openai-endpoint-doesnt-support-function-strict-setting/959
    """

    def __init__(self, schema: JsonSchema, *, strict: bool | None = None):
        super().__init__(schema, strict=None)
        self.is_strict_compatible = None  # Remove strict from generated schema
