"""LLM-as-judge for ConversationAgent eval tests."""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from chat.agents.base import BaseAgent

_JUDGE_SYSTEM_PROMPT = (
    "You are a strict but fair evaluator of AI assistant responses. "
    "You receive a response and a rubric. "
    "Answer ONLY with a JSON object matching the required schema: "
    "pass_ (boolean) and reason (short string). "
    "Set pass_=true only when the response clearly satisfies the rubric. "
    "Keep reason under 100 words."
)


class JudgeResult(BaseModel):
    pass_: bool = Field(alias="pass")
    reason: str

    model_config = {"populate_by_name": True}


class _JudgeAgent(BaseAgent):
    def get_system_prompt(self) -> str:
        return _JUDGE_SYSTEM_PROMPT

    def get_tools(self) -> list:
        return []


def create_judge(model_hrid: str) -> Agent:
    """Return a pydantic-ai Agent configured as an LLM judge."""
    return _JudgeAgent(model_hrid=model_hrid, output_type=JudgeResult)


async def judge_response(response: str, rubric: str, agent: Agent) -> JudgeResult:
    """Evaluate *response* against *rubric* and return a JudgeResult."""
    prompt = f"Rubric: {rubric}\n\nAssistant response to evaluate:\n{response}"
    result = await agent.run(prompt)
    return result.output
