"""
Unit tests for the ChatConversationRequestSerializer,
covering validation of chat conversation request data.
"""

import pytest
from rest_framework.exceptions import ErrorDetail

from chat import serializers
from chat.llm_configuration import LLModel, LLMProvider


@pytest.fixture(name="llm_configuration")
def llm_configuration_fixture(settings):
    """
    Define a simple model for tests.
    """
    settings.LLM_CONFIGURATIONS = {
        "model-1": LLModel(
            hrid="model-1",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon="base64encodediconstring",
            system_prompt="You are an amazing assistant.",
            tools=["web-search", "calculator"],
            provider=LLMProvider(hrid="unused", base_url="https://example.com", api_key="key"),
        ),
    }


def test_chat_conversation_request_serializer_default():
    """
    Test that the serializer validates default input and returns expected defaults.
    """
    serializer = serializers.ChatConversationRequestSerializer(data={})
    assert serializer.is_valid()
    assert serializer.validated_data == {
        "force_web_search": False,
        "model_hrid": None,
        "protocol": "data",
    }


@pytest.mark.parametrize(
    "protocol",
    ["data", "text"],
)
def test_chat_conversation_request_serializer_protocol_valid(protocol):
    """
    Test that the serializer accepts valid protocol values ('data', 'text').
    """
    serializer = serializers.ChatConversationRequestSerializer(data={"protocol": protocol})
    assert serializer.is_valid()


def test_chat_conversation_request_serializer_protocol_invalid():
    """
    Test that the serializer rejects invalid protocol values.
    """
    serializer = serializers.ChatConversationRequestSerializer(data={"protocol": "invalid"})
    assert not serializer.is_valid()
    assert serializer.errors == {
        "protocol": [
            ErrorDetail(string="Protocol must be either 'text' or 'data'.", code="invalid")
        ]
    }


@pytest.mark.parametrize(
    "force_web_search",
    [True, False],
)
def test_chat_conversation_request_serializer_force_web_search_valid(force_web_search):
    """
    Test that the serializer accepts valid boolean values for force_web_search.
    """
    serializer = serializers.ChatConversationRequestSerializer(
        data={"force_web_search": force_web_search}
    )
    assert serializer.is_valid()
    assert serializer.validated_data["force_web_search"] == force_web_search


def test_chat_conversation_request_serializer_force_web_search_invalid():
    """
    Test that the serializer rejects non-boolean values for force_web_search.
    """
    serializer = serializers.ChatConversationRequestSerializer(data={"force_web_search": "invalid"})
    assert not serializer.is_valid()
    assert serializer.errors == {
        "force_web_search": [ErrorDetail(string="Must be a valid boolean.", code="invalid")]
    }


def test_chat_conversation_request_serializer_model_hrid_valid(llm_configuration):  # pylint: disable=unused-argument
    """
    Test that the serializer accepts a valid model_hrid.
    """
    serializer = serializers.ChatConversationRequestSerializer(data={"model_hrid": "model-1"})
    assert serializer.is_valid()
    assert serializer.validated_data["model_hrid"] == "model-1"


def test_chat_conversation_request_serializer_model_hrid_invalid(llm_configuration):  # pylint: disable=unused-argument
    """
    Test that the serializer rejects an invalid model_hrid.
    """
    serializer = serializers.ChatConversationRequestSerializer(data={"model_hrid": "invalid"})
    assert not serializer.is_valid()
    assert serializer.errors == {
        "model_hrid": [ErrorDetail(string="Invalid model_hrid.", code="invalid")]
    }
