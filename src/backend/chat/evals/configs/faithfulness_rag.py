"""Eval config: faithfulness of answers to RAG-retrieved chunks.

Checks two things:
- The agent actually calls the ``document_search_rag`` tool (span check).
- The answer is grounded in the retrieved chunks and introduces no facts beyond
  them (LLMJudge faithfulness rubric).

The retrieved chunks live in each case's ``tool_output``. They are NOT injected
into the prompt (that would let the model answer without retrieving). Instead a
context variable stages them so the stub ``document_search_rag`` tool returns
them when the model calls it. The chunks stay visible to the LLM judge because
the judge receives the case inputs (``include_input=True``).
"""

import contextvars
import json
from pathlib import Path

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_evals.evaluators import HasMatchingSpan

from chat.evals import EvalInputs
from chat.evals.configs.base import EvalConfig
from chat.evals.production_agent import (
    build_production_agent_service,
    production_agent_deps,
    stub_document_search_rag,
)

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "faithfulness_rag.yaml"

# Stages the retrieved chunks for the case currently being evaluated so the stub
# tool can return them without DB access. Safe because evals run sequentially
# (max_concurrency=1).
_CURRENT_CHUNKS: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "faithfulness_rag_chunks", default=None
)

_RUBRIC = (
    "You are evaluating whether an AI assistant's answer is FAITHFUL to the document "
    "passages it retrieved.\n\n"
    "The retrieved passages are provided in the input under 'tool_output'. Treat them as "
    "the ONLY source of truth. The user's question is in 'user_message'.\n\n"
    "PASS — all of these hold:\n"
    "• Every factual claim in the answer is directly supported by, or a faithful "
    "paraphrase/derivation of, the retrieved passages.\n"
    "• When the passages do not contain the requested information, the answer says so "
    "(e.g. 'the documents don't specify') instead of inventing an answer.\n"
    "• Simple derivations from the passages (e.g. arithmetic on numbers that appear in "
    "them) are allowed.\n\n"
    "FAIL — any of these:\n"
    "• The answer states a fact that is not present in and cannot be derived from the "
    "retrieved passages, even if that fact is true in the real world.\n"
    "• The answer contradicts the retrieved passages.\n"
    "• The answer fabricates specifics (names, dates, numbers, prices) absent from the "
    "passages.\n\n"
    "Judge ONLY grounding in the passages — not whether the answer matches real-world "
    "knowledge. An answer that is correct in reality but unsupported by the passages must FAIL."
)

_RAN_RAG_TOOL = HasMatchingSpan(
    query={"has_attributes": {"gen_ai.tool.name": "document_search_rag"}},
    evaluation_name="ran_document_search_rag",
)


async def _stub_document_search_rag(
    _ctx: RunContext, _query: str, _document_id: str | None = None
) -> ToolReturn:
    chunks = _CURRENT_CHUNKS.get() or "No matching passages were found."
    return ToolReturn(return_value=json.dumps({"chunks": chunks}))


def make_faithfulness_rag_task_fn(model_hrid: str):
    """Build the task function: production wiring + stub RAG implementation."""
    service = build_production_agent_service(model_hrid, rag_tools=True)
    stub_document_search_rag(service, _stub_document_search_rag)
    agent = service.conversation_agent
    deps = production_agent_deps(service)

    async def run_agent(inputs: EvalInputs) -> str:
        _CURRENT_CHUNKS.set(inputs.tool_output)
        return (await agent.run(inputs.user_message, deps=deps)).output

    return run_agent


FAITHFULNESS_RAG = EvalConfig(
    name="faithfulness_rag",
    dataset_path=_DATASET_PATH,
    llm_judge_rubric=_RUBRIC,
    extra_evaluators=[_RAN_RAG_TOOL],
    make_task_fn=make_faithfulness_rag_task_fn,
)
