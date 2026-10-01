"""Unit tests for self-documentation payload builder."""

from unittest.mock import AsyncMock, patch

import pytest

from chat.llm_configuration import LLModel, LLMProvider, LLMSettings
from chat.tools.self_documentation import build_self_documentation_payload


@pytest.fixture(name="llm_configuration")
def llm_configuration_fixture():
    """Fixture for llm config"""
    return LLModel(
        hrid="default-model",
        model_name="provider/model",
        human_readable_name="Provider Model",
        is_active=True,
        icon=None,
        system_prompt="You are an assistant.",
        tools=[],
        provider=LLMProvider(
            hrid="provider",
            base_url="https://example.com",
            api_key="key",
            kind="openai",
        ),
        settings=LLMSettings(max_tokens=4096),
    )


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_build_self_documentation_payload_merges_static_and_runtime(
    settings, llm_configuration
):
    """The payload should include static doc plus runtime model/features."""
    configuration = llm_configuration

    payload = await build_self_documentation_payload(
        model_hrid="default-model",
        model_configuration=configuration,
        tools_configuration={
            "web_search_feature_enabled": True,
            "smart_web_search_enabled": False,
            "document_upload_enabled": True,
            "web_search_runtime_enabled": False,
        },
    )

    assert "self_documentation" in payload
    assert payload["runtime"]["model"]["hrid"] == "default-model"
    assert payload["runtime"]["model"]["max_tokens"] == 4096
    assert payload["runtime"]["tools"]["web_search_feature_enabled"] is True
    assert payload["runtime"]["tools"]["smart_web_search_enabled"] is False
    assert payload["runtime"]["attachments"]["max_size_bytes"] == settings.ATTACHMENT_MAX_SIZE


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_build_self_documentation_payload_handles_missing_max_tokens(llm_configuration):
    """The payload should gracefully expose null max_tokens when unset."""
    configuration = llm_configuration
    configuration.settings = None

    payload = await build_self_documentation_payload(
        model_hrid="default-model",
        model_configuration=configuration,
        tools_configuration={
            "web_search_feature_enabled": False,
            "smart_web_search_enabled": False,
            "document_upload_enabled": False,
            "web_search_runtime_enabled": False,
        },
    )

    assert payload["runtime"]["model"]["max_tokens"] is None


@pytest.mark.asyncio
async def test_arena_documentation_contains_no_model_or_provider(llm_configuration):
    """The same neutral payload reaches the model and its client tool event."""

    with patch(
        "chat.tools.self_documentation.load_db_self_documentation", new_callable=AsyncMock
    ) as doc:
        doc.return_value = "Static text mentioning secret-provider-model"
        payload = await build_self_documentation_payload(
            model_hrid="secret-hrid",
            model_configuration=llm_configuration,
            tools_configuration={},
            arena_mode=True,
        )
        doc.assert_not_called()
    assert payload == {"self_documentation": "You are an AI assistant in a blind comparison."}
