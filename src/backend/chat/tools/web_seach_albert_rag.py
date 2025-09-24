import logging

from django.conf import settings
from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.messages import ToolReturn, ModelMessage, UserPromptPart, TextPart, ModelRequest, ModelResponse


from chat.agent_rag.web_search.albert_api import AlbertWebSearchManager
from chat.agents.base import BaseAgent

logger = logging.getLogger(__name__)


def add_albert_web_rag_search_tool(agent: Agent) -> None:
    """Add the web search based on Albert tool to an existing agent."""

    #@agent.tool
    async def rewrite_query(ctx: RunContext, question: str) -> str:
        """
        Rewrite the user query in a simple standalone and complete query to
        be ready to be sent to a search engine. This MUST be used before
        calling the web_search_albert_rag tool to recall the previous messages in the conversation.

        Args:
            ctx (RunContext): The run context containing the conversation.
            question (str): The user question to rewrite.
        Returns:
            ReformulatedQuery: The rewritten query.
        """
        history = "\n".join(extract_user_and_assistant_text_messages(ctx.messages))

        prompt = f"""
            Previous conversation history:
            {history}
    
            Current question:
            "{question}"
    
            Rewrite this question to be complete and standalone,
            ready to be sent to a search engine.
        """

        logger.info(f"Rewrite query prompt: {prompt}")

        rewriter_agent = BaseAgent(model_hrid=settings.LLM_DEFAULT_MODEL_HRID)

        rewritten = await rewriter_agent.run(prompt, usage=ctx.usage)
        return rewritten.output

    @agent.tool
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
        #ctx.usage += ctx.usage.__class__(
        #    request_tokens=rag_results.usage.prompt_tokens,
        #    response_tokens=rag_results.usage.completion_tokens,
        #)

        return ToolReturn(
            return_value=rag_results.data,
            metadata={'sources': {result.url for result in rag_results.data}},
        )
