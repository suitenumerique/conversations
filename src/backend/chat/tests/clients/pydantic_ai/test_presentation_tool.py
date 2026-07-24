"""Tests for presentation tool feature-flag gating in AIAgentService."""

# pylint: disable=protected-access,redefined-outer-name
import pytest

from core.feature_flags.flags import FeatureToggle

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider, LLMSettings

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True, name="ai_settings")
def ai_settings_fixture(settings):
    """Minimal LLM configuration so the service can build its agent."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
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
            settings=LLMSettings(max_tokens=1024),
        )
    }
    return settings


def test_presentation_tool_registered_when_flag_enabled(feature_flags):
    """The tool is available on the agent when the feature flag is enabled."""
    feature_flags.presentation_generation = FeatureToggle.ENABLED
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    service._setup_presentation_tool()

    assert "generate_presentation" in service.conversation_agent._function_toolset.tools


def test_presentation_tool_absent_when_flag_disabled(feature_flags):
    """The tool is not registered when the feature flag is disabled."""
    feature_flags.presentation_generation = FeatureToggle.DISABLED
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    service._setup_presentation_tool()

    assert "generate_presentation" not in service.conversation_agent._function_toolset.tools
