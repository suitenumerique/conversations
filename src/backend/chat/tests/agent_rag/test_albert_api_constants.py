"""Test suite for albert_api_constants.py."""

import pytest
from pydantic import ValidationError

from chat.agent_rag.albert_api_constants import (
    SearchArgs,
    SearchMethod,
    SearchRequest,
)


def test_search_request_model_dump_json():
    """Test that SearchRequest.model_dump(mode='json') works correctly."""
    search_request = SearchRequest(prompt="test prompt")
    assert search_request.model_dump(mode="json") == {
        "collections": [],
        "k": 4,
        "method": "semantic",
        "prompt": "test prompt",
        "rff_k": 20,
        "score_threshold": 0.0,
        "web_search": False,
        "web_search_k": 5,
    }


def test_search_args_score_threshold_valid():
    """Test that score_threshold is valid for semantic and multiagent search methods."""
    try:
        SearchArgs(method=SearchMethod.SEMANTIC, score_threshold=0.5)
        SearchArgs(method=SearchMethod.MULTIAGENT, score_threshold=0.5)
    except ValidationError:
        pytest.fail("ValidationError was raised unexpectedly for valid search methods.")


def test_search_args_score_threshold_invalid():
    """Test that score_threshold raises ValueError for hybrid and lexical search methods."""
    with pytest.raises(ValidationError) as excinfo:
        SearchArgs(method=SearchMethod.HYBRID, score_threshold=0.5)
    assert "Score threshold is only available for semantic and multiagent search methods." in str(
        excinfo.value
    )

    with pytest.raises(ValidationError) as excinfo:
        SearchArgs(method=SearchMethod.LEXICAL, score_threshold=0.5)
    assert "Score threshold is only available for semantic and multiagent search methods." in str(
        excinfo.value
    )


def test_search_args_no_score_threshold():
    """Test that no error is raised when score_threshold is not set."""
    try:
        SearchArgs(method=SearchMethod.HYBRID)
        SearchArgs(method=SearchMethod.LEXICAL)
        SearchArgs(method=SearchMethod.SEMANTIC)
        SearchArgs(method=SearchMethod.MULTIAGENT)
    except ValidationError:
        pytest.fail("ValidationError was raised unexpectedly when score_threshold is not set.")
