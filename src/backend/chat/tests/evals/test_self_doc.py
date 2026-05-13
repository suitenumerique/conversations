"""
Eval tests for the self_documentation tool trigger behaviour (Groups A and B).

Run with: RUN_EVAL_TESTS=1 pytest -m eval src/backend/chat/tests/evals/test_self_doc.py -v
"""

import os

import pytest
from pydantic_ai.messages import ToolCallPart

from chat.tests.evals.dataset import SELF_DOC_NO_TRIGGER_CASES, SELF_DOC_TRIGGER_CASES

pytestmark = [
    pytest.mark.eval,
    pytest.mark.asyncio,
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.getenv("RUN_EVAL_TESTS"),
        reason="Set RUN_EVAL_TESTS=1 to run eval tests against a real LLM",
    ),
]


def _get_called_tools(result) -> list[str]:
    return [
        part.tool_name
        for msg in result.all_messages()
        for part in msg.parts
        if isinstance(part, ToolCallPart)
    ]


@pytest.mark.parametrize("case", SELF_DOC_TRIGGER_CASES, ids=lambda c: c.id)
async def test_self_documentation_triggered(case, self_doc_agent):
    """Group A: model must call self_documentation for meta questions."""
    result = await self_doc_agent.run(case.input)
    called = _get_called_tools(result)
    assert "self_documentation" in called, (
        f"[{case.id}] Expected self_documentation call for: {case.input!r}\n"
        f"Tools called: {called}\n"
        f"Response: {result.output!r}"
    )


@pytest.mark.parametrize("case", SELF_DOC_NO_TRIGGER_CASES, ids=lambda c: c.id)
async def test_self_documentation_not_triggered(case, conversation_agent):
    """Group B: model must NOT call self_documentation for regular tasks."""
    result = await conversation_agent.run(case.input)
    called = _get_called_tools(result)
    assert "self_documentation" not in called, (
        f"[{case.id}] Unexpected self_documentation call for: {case.input!r}\n"
        f"Tools called: {called}\n"
        f"Response: {result.output!r}"
    )
