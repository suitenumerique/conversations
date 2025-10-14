"""Common test fixtures for chat application tests."""

import logging
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import pytest

from chat.clients.pydantic_ai import AIAgentService

logger = logging.getLogger(__name__)


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
