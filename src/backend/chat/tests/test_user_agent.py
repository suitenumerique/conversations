"""The User-Agent Conversations sends on its outgoing LLM and MCP calls."""

# pylint: disable=protected-access
import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

import pytest
from pydantic_ai import Agent

from chat.agents.base import prepare_custom_model
from chat.llm_configuration import LLModel, LLMProvider
from chat.mcp_servers import DataGouvConnector
from chat.user_agent import get_user_agent

_COMPLETION = json.dumps(
    {
        "id": "completion",
        "object": "chat.completion",
        "created": 0,
        "model": "model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
).encode()


@pytest.fixture(name="recorder")
def recorder_fixture():
    """Serve on localhost, answer every POST with a chat completion, and record
    the User-Agent values of each request."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        """Record the User-Agent header, then answer."""

        def do_POST(self):  # pylint: disable=invalid-name
            """Answer a POST with a minimal chat completion."""
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            seen.append(self.headers.get_all("User-Agent"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(_COMPLETION)))
            self.end_headers()
            self.wfile.write(_COMPLETION)

        def log_message(self, *args):  # pylint: disable=arguments-differ
            """Keep test output quiet."""

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_user_agent_defaults_to_the_release(settings):
    """With no override, the User-Agent names Conversations and its release."""
    settings.OUTGOING_USER_AGENT = ""

    assert get_user_agent() == f"conversations/{settings.RELEASE}"


def test_user_agent_can_be_overridden(settings):
    """A deployment can replace the User-Agent, e.g. to add a contact URL."""
    settings.OUTGOING_USER_AGENT = "conversations/1.0 (+https://example.gouv.fr)"

    assert get_user_agent() == "conversations/1.0 (+https://example.gouv.fr)"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,co2_handling",
    [("mistral", None), ("openai", None), ("openai", "albert")],
    ids=["mistral", "openai", "albert"],
)
async def test_llm_calls_send_our_user_agent(settings, recorder, kind, co2_handling):
    """Each custom LLM provider sends exactly our User-Agent on the wire,
    not the one pydantic-ai or the provider SDK would set."""
    settings.OUTGOING_USER_AGENT = "conversations-test/1.0"
    url, seen = recorder
    model = prepare_custom_model(
        LLModel(
            hrid="model",
            model_name="model",
            human_readable_name="Model",
            is_active=True,
            system_prompt="You are a test.",
            tools=[],
            provider=LLMProvider(
                hrid=kind,
                kind=kind,
                base_url=f"{url}/v1",
                api_key="key",
                **({"co2_handling": co2_handling} if co2_handling else {}),
            ),
        )
    )

    # Only the request matters here, not whether this SDK accepts the reply.
    with contextlib.suppress(Exception):
        await Agent(model).run("hello")

    assert seen
    assert seen[0] == ["conversations-test/1.0"]


@pytest.mark.asyncio
async def test_mcp_connector_sends_our_user_agent(settings, recorder):
    """The data.gouv MCP client sends our User-Agent on the wire."""
    settings.OUTGOING_USER_AGENT = "conversations-test/1.0"
    url, seen = recorder
    settings.DATAGOUV_CONNECTOR_URL = f"{url}/mcp"
    settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT = 2.0

    toolset = DataGouvConnector(conversation_pk=uuid4(), enabled=True, opted_in=True).toolsets()[0]

    # The recorder is no MCP server, so the handshake fails after its first request.
    with contextlib.suppress(Exception):
        async with toolset:
            pass

    assert seen
    assert seen[0] == ["conversations-test/1.0"]
