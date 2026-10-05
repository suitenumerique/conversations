"""The local LLM config carries the prod entries used by eval targets.

`custom_llm_configuration.json` is a per-developer file (globally gitignored);
these checks only run where it exists.
"""

import json
from pathlib import Path

import pytest

CONFIG_PATH = (
    Path(__file__).resolve().parents[4]
    / "conversations/configuration/llm/custom_llm_configuration.json"
)

pytestmark = pytest.mark.skipif(
    not CONFIG_PATH.exists(), reason="local custom_llm_configuration.json not present"
)


@pytest.fixture(name="models")
def models_fixture():
    """Model entries by hrid."""
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {model["hrid"]: model for model in data["models"]}


@pytest.mark.parametrize(
    ("hrid", "model_name", "max_token_context"),
    [
        ("albert-mistral-medium-2508", "mistral-medium-2508", 128000),
        ("mistral-medium-3-5", "mistral-medium-3-5", 131072),
    ],
)
def test_prod_chat_models(models, hrid, model_name, max_token_context):
    """Chat models match prod: Albert provider, prod context size, Brave web search."""
    model = models[hrid]

    assert model["model_name"] == model_name
    assert model["provider_name"] == "albert"
    assert model["max_token_context"] == max_token_context
    assert model["settings"] == {}
    assert model["web_search"] == "chat.tools.web_search_brave.web_search_brave_llm_context"
    assert "based on Mistral Medium 2508" in model["system_prompt"]


def test_prod_summarization_model(models):
    """summarize chunk/merge runs on the real mistral-medium-2508 (Mistral API) in every cell.

    Albert's 2508 alias now serves mistral-medium-3-5, so the July setup needs Mistral's API.
    """
    model = models["default-summarization-model"]

    assert model["model_name"] == "mistral-medium-2508"
    assert model["provider_name"] == "mistral"
    assert model["system_prompt"] == "settings.SUMMARIZATION_SYSTEM_PROMPT"
