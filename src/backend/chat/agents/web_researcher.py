"""Web research sub-agent: runs several searches and keeps only relevant sources."""

import asyncio
import dataclasses
from datetime import UTC, datetime

from django.utils.module_loading import import_string

from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolReturn, ToolReturnPart
from pydantic_ai.tools import ToolDefinition

from chat.clients.schema import ContextDeps
from chat.tools.exceptions import ModelCannotRetry

from .base import BaseAgent

# Hard limits, enforced by SubAgents: reaching one discards the research.
RESEARCH_TOKEN_BUDGET = 150_000
RESEARCH_TIMEOUT_SECONDS = 120
# Soft limits: past any one, searching stops and the researcher reports what it has.
# The margins leave room for that last request, which carries the whole context.
WRAP_UP_TOKENS = 100_000
WRAP_UP_SECONDS = 85
MAX_SEARCH_ROUNDS = 3
MAX_QUERIES_PER_ROUND = 4

WRAP_UP_INSTRUCTIONS = """
Searching is over: do not search any more. Report now with what you have
found, and list in `gaps` the parts of the task that remain unanswered.
"""

WEB_RESEARCHER_DESCRIPTION = (
    "Researches a question on the web: runs several focused searches, discards "
    "irrelevant sources, and returns sourced facts. Give it a self-contained task "
    "including the user's question and any useful context from the conversation."
)

WEB_RESEARCHER_INSTRUCTIONS = f"""
You are a web research assistant. You receive one research task.

1. List the distinct facts the task needs. Search for all of them at once:
   one web_search call with one focused query per fact (up to
   {MAX_QUERIES_PER_ROUND} queries). You have {MAX_SEARCH_ROUNDS} search calls in total.
2. Search again only for facts still missing or contradicted, for example a
   fact that depends on one you just found (a person's name, then what they did).
   Never search only to find more or better-known sources for a fact you
   already have.
3. Read the results critically. Ignore sources that do not directly support
   a fact: off-topic pages, outdated information, low-quality or duplicate
   content. Prefer official and primary sources.
4. As soon as every part of the task is covered, report. Keep every relevant
   detail: exact figures, dates, names, amounts and context. The conversation
   agent only sees your findings, not the search results.

Each finding is one fact with the URL it comes from, copied exactly from the
search results.
"""


class Finding(BaseModel):
    """One fact and the search result it comes from."""

    fact: str = Field(description="The fact, with its exact figures, dates and names.")
    source: str = Field(description="URL of the search result stating this fact.")


class WebResearchFindings(BaseModel):
    """What the researcher reports back to the conversation agent."""

    findings: list[Finding] = Field(description="Facts that answer the task.")
    gaps: str | None = Field(
        default=None, description="Parts of the task the sources do not answer, if any."
    )

    def __str__(self) -> str:
        """Render for the conversation agent, which receives str(output)."""
        lines = ["Web research findings. Cite the source link next to each fact you use."]
        lines += [f"- {finding.fact} (source: {finding.source})" for finding in self.findings]
        if self.gaps:
            lines.append(f"Not found: {self.gaps}")
        return "\n".join(lines)


def _searched_urls(messages) -> set[str]:
    """Collect every URL returned by the web_search tool during the run."""
    return {
        url
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.metadata
        for url in part.metadata.get("sources", ())
    }


def _search_rounds(messages) -> int:
    """Count the web_search calls made during the run."""
    return sum(
        1
        for message in messages
        if isinstance(message, ModelResponse)
        for call in message.tool_calls
        if call.tool_name == "web_search"
    )


def _should_wrap_up(ctx: RunContext) -> bool:
    """Whether searching is over: rounds used up, or close to the hard limits."""
    if _search_rounds(ctx.messages) >= MAX_SEARCH_ROUNDS:
        return True
    if ctx.usage.total_tokens >= WRAP_UP_TOKENS:
        return True
    started_at = ctx.messages[0].timestamp if ctx.messages else None
    return (
        started_at is not None
        and (datetime.now(UTC) - started_at).total_seconds() >= WRAP_UP_SECONDS
    )


async def _hide_when_wrapping_up(
    ctx: RunContext, tool_def: ToolDefinition
) -> ToolDefinition | None:
    """Withdraw web_search so the only move left is to report."""
    return None if _should_wrap_up(ctx) else tool_def


@dataclasses.dataclass(init=False)
class WebResearcherAgent(BaseAgent):
    """Child agent delegated web research by the conversation agent."""

    def __init__(self, *, model_hrid, **kwargs):
        super().__init__(
            model_hrid=model_hrid,
            name="web_researcher",
            description=WEB_RESEARCHER_DESCRIPTION,
            output_type=WebResearchFindings,
            deps_type=ContextDeps,
            **kwargs,
        )
        web_search_impl = import_string(self.configuration.web_search)

        @self.tool(name="web_search", retries=1, prepare=_hide_when_wrapping_up)
        async def web_search(ctx: RunContext, queries: list[str]) -> ToolReturn:
            """Search the web for several queries at once.

            Args:
                queries: One short, focused query per fact to find, at most 4.
                    Use site:example.com to restrict a query to a domain.
            """
            if not 0 < len(queries) <= MAX_QUERIES_PER_ROUND:
                raise ModelRetry(f"Pass between 1 and {MAX_QUERIES_PER_ROUND} queries.")

            async def search(query: str) -> ToolReturn | str:
                """One query; a failure is reported for that query only."""
                try:
                    return await web_search_impl(ctx, query)
                except (ModelRetry, ModelCannotRetry) as exc:
                    return f"Search failed: {exc.message}"

            results = await asyncio.gather(*(search(query) for query in queries))
            return ToolReturn(
                return_value={
                    query: result.return_value if isinstance(result, ToolReturn) else result
                    for query, result in zip(queries, results, strict=True)
                },
                metadata={
                    "sources": {
                        url
                        for result in results
                        if isinstance(result, ToolReturn) and result.metadata
                        for url in result.metadata.get("sources", ())
                    }
                },
            )

        @self.instructions
        def wrap_up(ctx: RunContext) -> str:
            """Tell the model to report once searching is withdrawn."""
            return WRAP_UP_INSTRUCTIONS if _should_wrap_up(ctx) else ""

        @self.output_validator
        def keep_searched_sources(
            ctx: RunContext[ContextDeps], output: WebResearchFindings
        ) -> WebResearchFindings:
            """Drop findings with invented URLs and hand their sources to the parent stream."""
            searched = _searched_urls(ctx.messages)
            if not searched and not _should_wrap_up(ctx):
                raise ModelRetry("Call web_search before answering.")
            output.findings = [finding for finding in output.findings if finding.source in searched]
            ctx.deps.web_research_sources.extend(
                dict.fromkeys(finding.source for finding in output.findings)
            )
            return output

    def get_system_prompt(self) -> str:
        return WEB_RESEARCHER_INSTRUCTIONS

    def get_tools(self) -> list:
        return []
