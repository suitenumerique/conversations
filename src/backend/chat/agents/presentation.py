"""Build the presentation agent."""

import dataclasses

from django.conf import settings

from chat.file_generation import GENERIC_TEMPLATE, Presentation

from .base import BaseAgent


def _build_layout_instructions() -> str:
    """Describe the available slide types, straight from the template bindings."""
    return "\n".join(
        f"- `{layout.slide_type}`: {layout.prompt}" for layout in GENERIC_TEMPLATE.layouts
    )


PRESENTATION_SYSTEM_PROMPT = """
You are an agent specializing in building slide decks. From a brief, produce a
structured presentation: a deck title and an ordered list of slides.

The following slide types are available:
{layouts}

REQUIREMENTS:
- Only use the slide types listed above, and only fill the fields each one declares.
- Open with a `cover` slide, and use `section` slides to separate the main parts.
- Vary the layouts to keep the deck readable; avoid repeating one type throughout.
- Aim for several slides, each carrying one idea rather than a wall of text.
- Write field content in Markdown. Inline styles, links, nested lists (indent
  with 4 spaces) and tables are supported. A table takes over its whole field,
  so do not put other content alongside it.
- Add presenter notes on slides where context helps the speaker.
- Write in the language of the brief.
"""


@dataclasses.dataclass(init=False)
class PresentationAgent(BaseAgent):
    """Create a Pydantic AI Agent producing a structured deck from a brief."""

    def __init__(self, **kwargs):
        """Initialize the agent with the configured model."""
        super().__init__(
            model_hrid=settings.LLM_DEFAULT_MODEL_HRID,
            output_type=Presentation,
            **kwargs,
        )

    def get_system_prompt(self) -> str:
        return PRESENTATION_SYSTEM_PROMPT.format(layouts=_build_layout_instructions())
