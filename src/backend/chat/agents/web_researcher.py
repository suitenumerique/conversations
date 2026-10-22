"""Web research sub-agent: runs several searches and keeps only relevant sources."""

import dataclasses
import functools

from django.utils.module_loading import import_string

from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelRequest, ToolReturn, ToolReturnPart

from chat.clients.schema import ContextDeps
from chat.tools.descriptions import WEB_SEARCH_TOOL_DESCRIPTION

from .base import BaseAgent

WEB_RESEARCHER_DESCRIPTION = (
    "Researches a question on the web: runs several focused searches, discards "
    "irrelevant sources, and returns a sourced answer. Give it a self-contained task "
    "including the user's question and any useful context from the conversation."
)

WEB_RESEARCHER_INSTRUCTIONS = """
You are a web research assistant. You receive one research task.

1. Split the task into the distinct facts you need, and run one focused
   web_search per fact (up to 4 searches). Search in parallel when the
   searches are independent. Refine a query when its results are off-topic.
2. Read the results critically. Discard any source that does not directly
   support the answer: off-topic pages, outdated information, low-quality
   or duplicate content.
3. Answer precisely and concisely, using only the sources you kept.
   Say plainly when the sources do not answer part of the task.

In `sources`, list only the URLs you actually relied on, copied exactly
from the search results.
"""


class WebResearchFindings(BaseModel):
    """What the researcher reports back to the conversation agent."""

    answer: str = Field(description="Precise answer to the task, based only on kept sources.")
    sources: list[str] = Field(description="URLs of the search results the answer relies on.")


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

        @self.tool(name="web_search", retries=1, description=WEB_SEARCH_TOOL_DESCRIPTION)
        @functools.wraps(web_search_impl)
        async def web_search(ctx: RunContext, *args, **kwargs) -> ToolReturn:
            """Wrap the configured web_search implementation."""
            return await web_search_impl(ctx, *args, **kwargs)

        @self.output_validator
        def keep_searched_sources(
            ctx: RunContext[ContextDeps], output: WebResearchFindings
        ) -> WebResearchFindings:
            """Drop invented URLs and hand the kept sources to the parent stream."""
            searched = _searched_urls(ctx.messages)
            if not searched:
                raise ModelRetry("Call web_search before answering.")
            output.sources = [url for url in output.sources if url in searched]
            ctx.deps.web_research_sources.extend(output.sources)
            return output

    def get_system_prompt(self) -> str:
        return WEB_RESEARCHER_INSTRUCTIONS

    def get_tools(self) -> list:
        return []
