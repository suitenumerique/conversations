"""
Eval tests verifying that standard agent capabilities are not degraded
by the new instructions (Group E).

Uses an LLM-as-judge to assess response quality.

Run with: RUN_EVAL_TESTS=1 pytest -m eval src/backend/chat/tests/evals/test_regression.py -v
"""

import os

import pytest

from chat.tests.evals.dataset import REGRESSION_CASES

pytestmark = [
    pytest.mark.eval,
    pytest.mark.asyncio,
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.getenv("RUN_EVAL_TESTS"),
        reason="Set RUN_EVAL_TESTS=1 to run eval tests against a real LLM",
    ),
]


@pytest.mark.parametrize("case", REGRESSION_CASES, ids=lambda c: c.id)
async def test_no_regression(case, conversation_agent, judge):
    """Group E: standard tasks must still produce coherent, useful responses."""
    result = await conversation_agent.run(case.input)
    response = result.output
    verdict = await judge(response, case.judge_rubric)
    assert verdict.pass_, (
        f"[{case.id}] Judge FAIL.\n"
        f"Input: {case.input!r}\n"
        f"Rubric: {case.judge_rubric}\n"
        f"Reason: {verdict.reason}\n"
        f"Response: {response!r}"
    )
