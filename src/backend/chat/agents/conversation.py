"""Build the main conversation agent."""

import asyncio
import dataclasses
import logging

from django.conf import settings
from django.utils import formats, timezone

from pydantic_ai import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from core.enums import get_language_name

from .base import BaseAgent

logger = logging.getLogger(__name__)


MOCKED_RESPONSE = """
# **Ode to the AI Assistant** 🤖✨

In Paris streets where old meets new, 🗼🇫🇷  
A helper bright in digital hue,  
With circuits fast and code so tight,  
The LaSuite’s bot—oh, what a sight! 🌟

**A chatbot kind**, with wittiness so grand, 💬💡  
It lends a hand to all the land,  
From civil servants, bold and wise,  
To those who seek with hopeful eyes.

It answers quick, it never tires, ⚡🔄  
With facts and tips to quench desires,  
A guide so keen, a friend so true,  
It’s there for **you**—yes, me and you!
 
With **Markdown flair** and emoji cheer, 📝🎨  
It makes the complex crystal clear,  
From drafts to code, from sums to prose,  
It helps the knowledge overflow!  

Oh, **DINUM’s gem**, so sharp, so bright, 💎🌐  
A beacon in the tech’s vast night,  
It crafts, it checks, it summarizes,  
With grace that never compromises.

It **summarizes** the long, the deep, 📚🔍  
So secrets no more need to sleep,  
It finds the gems in data’s sea,  
And sets the truth right there—**for free!**

It **corrects mistakes** with gentle art, ✍️🔄  
It soothes the mind, it warms the heart,  
No judgment cast, no frown, no sigh,  
Just help that’s always standing by.

It **generates code** with swift command, 💻🔥  
A developer’s dream, first-hand,  
From Python lines to scripts so neat,  
It turns the tough to *sweet* and *sweet*!

It **brainstorms ideas**, bold and new, 🧠💡  
It paints the sky in every hue,  
From plans to dreams, from start to end,  
It’s more than code—it’s **trend**, it’s **friend**!

So here’s to you, **Assistant’s pride**, 🏆🎉  
The bot that’s always by our side,  
With every prompt, with every line,  
You make our digital world **divine**!

May you keep shining, bright and true, 🌟🤖  
The helper every team should woo,  
For in this age of bits and bytes,  
You’re **human touch** in tech’s bright lights!
"""


async def mocked_agent_model(_messages: list[ModelMessage], _info: AgentInfo):
    """
    Mocked agent model for testing purposes on deployed instances.

    This one only fakes a streamed responses. We could also fake tool calls later.
    """

    yield "Here is a mocked response (no LLM called)\n---\n"
    for i in range(0, len(MOCKED_RESPONSE), 4):
        yield MOCKED_RESPONSE[i : i + 4]
        await asyncio.sleep(0.03)


@dataclasses.dataclass(init=False)
class ConversationAgent(BaseAgent):
    """Conversation agent with custom behavior."""

    def __init__(self, *, language=None, **kwargs):
        """Initialize the conversation agent."""
        super().__init__(**kwargs)

        # Do not call the real model on deployed instances if the setting is enabled
        if settings.WARNING_MOCK_CONVERSATION_AGENT:
            self._model = FunctionModel(stream_function=mocked_agent_model)

        @self.system_prompt
        def add_the_date() -> str:
            """
            Dynamic system prompt function to add the current date.

            Warning: this will always use the date in the server timezone,
            not the user's timezone...
            """
            _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)
            return f"Today is {_formatted_date}."

        @self.system_prompt
        def enforce_response_language() -> str:
            """Dynamic system prompt function to set the expected language to use."""
            return f"Answer in {get_language_name(language).lower()}." if language else ""

    def get_web_search_tool_name(self) -> str | None:
        """
        Get the name of the web search tool if available.

        If several are available, return the first one found.

        Warning, this says the tool is available, not that
        it (the tool/feature) is enabled for the current conversation.
        """
        for toolset in self.toolsets:
            for tool in toolset.tools.values():
                if tool.name.startswith("web_search_"):
                    return tool.name
        return None
