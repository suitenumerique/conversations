"""Tool to perform web search using Albert API."""

from pydantic_ai import RunContext, RunUsage
from pydantic_ai.messages import (
    ToolReturn,
)

from chat.agent_rag.web_search.albert_api import AlbertWebSearchManager


async def web_search_albert_rag(ctx: RunContext, query: str) -> ToolReturn:
    """
    Call me to perform a web search.
    Must be used whenever the user asks for information that
    is not in the model's knowledge base or regarding specific topics.

    Args:
        ctx (RunContext): The run context containing the conversation.
        query (str): The search query.
    """
    rag_results = AlbertWebSearchManager().web_search(query)

    ctx.usage += RunUsage(
        input_tokens=rag_results.usage.prompt_tokens,
        output_tokens=rag_results.usage.completion_tokens,
    )

    return ToolReturn(
        return_value=rag_results.data,
        metadata={"sources": [result.url for result in rag_results.data]},
    )
