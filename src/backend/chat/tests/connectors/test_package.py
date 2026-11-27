"""Where connector code lives, and which names it no longer has."""

import importlib
import pathlib

import pytest

import core

import chat

CHAT_DIR = pathlib.Path(chat.__file__).parent
CORE_DIR = pathlib.Path(core.__file__).parent

# Code that handles every connector alike: none of it may know data.gouv by name.
GENERIC_MODULES = [
    CHAT_DIR / "clients/pydantic_ai.py",
    CHAT_DIR / "turn/event_mapper.py",
    CHAT_DIR / "serializers.py",
    CHAT_DIR / "views/conversations.py",
    CORE_DIR / "api/serializers.py",
    CORE_DIR / "api/viewsets.py",
    *sorted((CHAT_DIR / "connectors").glob("*.py")),
]


@pytest.mark.parametrize("module", GENERIC_MODULES, ids=lambda path: path.name)
def test_no_data_gouv_name_is_left_in_generic_code(module):
    """The agent, the stream and the APIs know connectors, not one connector in particular."""
    source = module.read_text(encoding="utf-8").lower()

    for name in ("datagouv", "data.gouv", "data_gouv"):
        assert name not in source, f"{name!r} is still in {module.name}"


@pytest.mark.parametrize("module", ["chat.mcp_servers", "chat.connectors.datagouv"])
def test_the_transitional_modules_are_gone(module):
    """The one-release shim and the data.gouv bridge are removed."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)
