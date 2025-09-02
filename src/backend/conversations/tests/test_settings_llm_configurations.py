"""Test that LLM_CONFIGURATIONS is cached in Production but not in Test configuration."""

from importlib.machinery import PathFinder
from unittest.mock import patch

from configurations.importer import ConfigurationLoader


def test_llm_configurations_is_cached_in_production():
    """In Production configuration, LLM_CONFIGURATIONS should be cached (only one load)."""
    with patch(
        "chat.llm_configuration.load_llm_configuration", return_value={"foo": "bar"}
    ) as mock_load:
        spec = PathFinder.find_spec(fullname="conversations.settings")
        settings = ConfigurationLoader("Production", spec).load_module("conversations.settings")

        # Two access to the property (inside the context, because it's lazy)
        config1 = settings.LLM_CONFIGURATIONS
        config2 = settings.LLM_CONFIGURATIONS

        assert config1 == config2  # run the lazy evaluation

    assert mock_load.call_count == 1


def test_llm_configurations_is_not_cached_in_test():
    """In Test configuration, LLM_CONFIGURATIONS should NOT be cached (two loads)."""
    with patch(
        "conversations.settings.load_llm_configuration", return_value={"foo": "bar"}
    ) as mock_load:
        spec = PathFinder.find_spec(fullname="conversations.settings")
        settings = ConfigurationLoader("Test", spec).load_module("conversations.settings")

        # Two access to the property (inside the context, because it's lazy)
        config1 = settings.LLM_CONFIGURATIONS
        config2 = settings.LLM_CONFIGURATIONS

        assert config1 == config2  # run the lazy evaluation

    assert mock_load.call_count == 2
