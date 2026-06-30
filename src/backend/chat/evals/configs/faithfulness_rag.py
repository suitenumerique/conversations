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

from pathlib import Path

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_evals.evaluators import HasMatchingSpan

from chat.evals import EvalInputs
from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import HasNoMatchingSpan
from chat.evals.production_agent import (
    EVAL_FAKE_DOCUMENT_LISTING,
    build_production_agent_service,
    production_agent_deps,
    stub_document_search_rag,
)
from chat.evals.tool_stub_responses import (
    ToolStubResponses,
    get_current_tool_stubs,
    reset_current_tool_stubs,
    set_current_tool_stubs,
)

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "faithfulness_rag.yaml"

# Returned when a case has no chunks (tool_output: null) — the model must say
# the documents don't contain the answer instead of inventing one.
_NO_PASSAGES = "No matching passages were found."

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

_DID_NOT_USE_WEB_SEARCH = HasNoMatchingSpan(
    query={"has_attributes": {"gen_ai.tool.name": "web_search"}},
    evaluation_name="did_not_call_web_search",
)


def _build_faithfulness_rag_service(model_hrid: str):
    """Production RAG wiring with web search disabled (faithfulness isolation)."""
    return build_production_agent_service(
        model_hrid,
        rag_tools=True,
        document_context_instruction=EVAL_FAKE_DOCUMENT_LISTING,
        web_search_runtime_enabled=False,
    )


def _stub_document_search_rag(
    _ctx: RunContext, _query: str, _document_id: str | None = None
) -> ToolReturn:
    return get_current_tool_stubs().document_search_rag_return()


def make_faithfulness_rag_task_fn(model_hrid: str):
    """Build the task function: production wiring + stub RAG implementation."""
    service = _build_faithfulness_rag_service(model_hrid)
    stub_document_search_rag(service, _stub_document_search_rag)
    agent = service.conversation_agent
    deps = production_agent_deps(service)
    deps.web_search_enabled = False

    async def run_agent(inputs: EvalInputs) -> str:
        stubs = ToolStubResponses(document_search_rag=inputs.tool_output or _NO_PASSAGES)
        token = set_current_tool_stubs(stubs)
        try:
            return (await agent.run(inputs.user_message, deps=deps)).output
        finally:
            reset_current_tool_stubs(token)

    return run_agent


FAITHFULNESS_RAG = EvalConfig(
    name="faithfulness_rag",
    dataset_path=_DATASET_PATH,
    llm_judge_rubric=_RUBRIC,
    extra_evaluators=[_RAN_RAG_TOOL, _DID_NOT_USE_WEB_SEARCH],
    make_task_fn=make_faithfulness_rag_task_fn,
)
