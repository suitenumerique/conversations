"""Where connector code lives, and the import path kept for one release."""

import pathlib

import pytest

import chat
from chat import mcp_servers
from chat.connectors import errors, runtime

CHAT_DIR = pathlib.Path(chat.__file__).parent


@pytest.mark.parametrize("module", ["clients/pydantic_ai.py", "turn/event_mapper.py"])
def test_no_data_gouv_name_is_left_in_the_turn_code(module):
    """The agent and the stream know connectors, not one connector in particular."""
    source = (CHAT_DIR / module).read_text(encoding="utf-8").lower()

    for name in ("datagouv", "data.gouv", "data_gouv"):
        assert name not in source, f"{name!r} is still in {module}"


def test_the_old_import_path_still_works():
    """`chat.mcp_servers` re-exports the runtime names for one release."""
    assert mcp_servers.ConnectorToolset is runtime.ConnectorToolset
    assert mcp_servers.enter_mcp_toolsets is runtime.enter_mcp_toolsets
    assert mcp_servers.is_connector_unreachable is errors.is_connector_unreachable
    assert mcp_servers.CONNECTOR_UNAVAILABLE_ERRORS is errors.CONNECTOR_UNAVAILABLE_ERRORS
