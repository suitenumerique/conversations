"""
Unit tests for the ChatConversationRequestSerializer,
covering validation of chat conversation request data.
"""

from django.http import QueryDict

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
        "force_connectors": [],
        "model_hrid": None,
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


def test_chat_conversation_request_serializer_force_connectors_from_query_params():
    """Several connectors are forced by repeating the query parameter."""
    serializer = serializers.ChatConversationRequestSerializer(
        data=QueryDict("force_connectors=datagouv&force_connectors=legi&force_connectors=legi")
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["force_connectors"] == ["datagouv", "legi"]


def test_chat_conversation_request_serializer_deprecated_force_datagouv():
    """`force_datagouv=true` still works, as `force_connectors=datagouv`."""
    serializer = serializers.ChatConversationRequestSerializer(
        data=QueryDict("force_datagouv=true&force_connectors=datagouv")
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["force_connectors"] == ["datagouv"]
    assert "force_datagouv" not in serializer.validated_data


@pytest.mark.parametrize("slug", ["Not A Slug", "a" * 21, ""])
def test_chat_conversation_request_serializer_force_connectors_rejects_bad_slugs(slug):
    """Only well-formed slugs; whether they are offered is the turn's call."""
    serializer = serializers.ChatConversationRequestSerializer(
        data=QueryDict(f"force_connectors={slug}")
    )

    assert not serializer.is_valid()
    assert "force_connectors" in serializer.errors


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
