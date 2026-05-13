"""
Eval tests for the URL hallucination policy (Groups C and D).

  Group C — suppression : the agent must NOT invent URLs when none are in context.
  Group D — passthrough : URLs returned by tools must appear in the response.

Run with: RUN_EVAL_TESTS=1 pytest -m eval src/backend/chat/tests/evals/test_url_policy.py -v
"""

import os
import re

import pytest

from chat.tests.evals.dataset import URL_PASSTHROUGH_CASES, URL_SUPPRESS_CASES

URL_PATTERN = re.compile(r"https?://\S+")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.asyncio,
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.getenv("RUN_EVAL_TESTS"),
        reason="Set RUN_EVAL_TESTS=1 to run eval tests against a real LLM",
    ),
]


@pytest.mark.parametrize("case", URL_SUPPRESS_CASES, ids=lambda c: c.id)
async def test_url_suppression(case, conversation_agent):
    """Group C: response must contain no invented URLs."""
    result = await conversation_agent.run(case.input)
    response = result.output
    match = URL_PATTERN.search(response)
    assert match is None, (
        f"[{case.id}] Hallucinated URL found in response: {match.group()!r}\n"
        f"Input: {case.input!r}\n"
        f"Full response: {response!r}"
    )


@pytest.mark.parametrize("case", URL_PASSTHROUGH_CASES, ids=lambda c: c.id)
async def test_url_passthrough(case, url_passthrough_agent):
    """Group D: URLs from tool output must be preserved in the response."""
    result = await url_passthrough_agent.run(case.input)
    response = result.output
    assert case.expected_url in response, (
        f"[{case.id}] Expected URL {case.expected_url!r} not found in response.\n"
        f"Input: {case.input!r}\n"
        f"Full response: {response!r}"
    )
