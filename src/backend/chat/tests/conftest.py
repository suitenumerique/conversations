"""Common test fixtures for chat application tests."""

import logging
from contextlib import ExitStack, contextmanager
from importlib import reload
from unittest.mock import patch

from django.urls import clear_url_caches, set_urlconf
from django.utils import formats, timezone

import pytest

import core.urls

import chat.views
import conversations.urls
from chat.agents.summarize import SummarizationAgent
from chat.clients.pydantic_ai import AIAgentService

logger = logging.getLogger(__name__)


@pytest.fixture(name="today_promt_date")
def today_prompt_date_fixture():
    """Fixture to mock date the system prompt when useless to test it."""
    _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)
    return f"Today is {_formatted_date}."


@pytest.fixture(name="mock_ai_agent_service")
def mock_ai_agent_service_fixture():
    """Fixture to mock AIAgentService with a custom model."""

    @contextmanager
    def _mock_service(model):
        """Context manager to mock AIAgentService with a custom model."""
        with ExitStack() as stack:

            class AIAgentServiceMock(AIAgentService):
                """Mocked AIAgentService to override the model."""

                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    # We cannot use stack.enter_context(agent.override(model=model))
                    # Because the agent is used outside of this context manager.
                    # So we directly override the protected member.
                    logger.info("Overriding AIAgentService model with %s", model)
                    self.conversation_agent._model = model  # pylint: disable=protected-access

            # Mock the AIAgentService in all relevant modules, because first import wins
            stack.enter_context(
                patch("chat.clients.pydantic_ai.AIAgentService", new=AIAgentServiceMock)
            )
            stack.enter_context(patch("chat.views.AIAgentService", new=AIAgentServiceMock))
            yield

    yield _mock_service


@pytest.fixture(name="mock_summarization_agent")
def mock_summarization_agent_fixture():
    """Fixture to mock SummarizationAgent with a custom model."""

    @contextmanager
    def _mock_agent(model):
        """Context manager to mock SummarizationAgent with a custom model."""
        with ExitStack() as stack:

            class SummarizationAgentMock(SummarizationAgent):
                """Mocked SummarizationAgent to override the model."""

                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    # We cannot use stack.enter_context(agent.override(model=model))
                    # Because the agent is used outside of this context manager.
                    # So we directly override the protected member.
                    logger.info("Overriding SummarizationAgent model with %s", model)
                    self._model = model  # pylint: disable=protected-access

            # Mock the SummarizationAgent in all relevant modules, because first import wins
            stack.enter_context(
                patch("chat.agents.summarize.SummarizationAgent", new=SummarizationAgentMock)
            )
            stack.enter_context(
                patch(
                    "chat.tools.document_summarize.SummarizationAgent", new=SummarizationAgentMock
                )
            )
            yield

    yield _mock_agent


PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00"
    b"\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(name="oidc_refresh_token_enabled")
def fixture_oidc_refresh_token_enabled(settings):
    """
    Fixture to enable OIDC refresh token storage during the test.

    This is not a nice fixture, as it forces reloading views and URL configurations.
    Maybe there is a better way to do this, because even the conditional_refresh_oidc_token
    function is not nice, but I don't want it to be lazy either.
    """
    __initial_value = bool(settings.OIDC_STORE_REFRESH_TOKEN)

    settings.OIDC_STORE_REFRESH_TOKEN = True

    # force view reload
    reload(chat.views)
    reload(core.urls)
    reload(conversations.urls)
    clear_url_caches()
    set_urlconf(None)

    yield settings

    settings.OIDC_STORE_REFRESH_TOKEN = __initial_value

    # force view reload
    reload(chat.views)
    reload(core.urls)
    reload(conversations.urls)
    clear_url_caches()
    set_urlconf(None)
