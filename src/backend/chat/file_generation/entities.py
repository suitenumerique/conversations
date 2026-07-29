"""Data structures describing a presentation and the template that renders it."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class SlideType(StrEnum):
    """Layout kinds a generated slide can use."""

    COVER = "cover"
    SECTION = "section"
    TITLE_ONE_COLUMN = "title_one_column"
    TITLE_TWO_COLUMNS = "title_two_columns"
    TITLE_THREE_COLUMNS = "title_three_columns"


class Slide(BaseModel):
    """
    A single slide.

    Every field but ``type`` is optional: which ones are meaningful depends on
    the slide type, and the mapping is declared by the ``SlideLayout`` bound to
    that type. Text fields hold Markdown, rendered by ``renderer.render``. The
    presentation agent's system prompt documents which field each type uses.
    """

    type: SlideType
    title: str = ""
    subtitle: str = ""
    content: str = ""
    left: str = ""
    center: str = ""
    right: str = ""
    slide_notes: str = ""


class Presentation(BaseModel):
    """A whole deck, as produced by the presentation agent."""

    title: str
    slides: list[Slide] = Field(min_length=1)


@dataclass(frozen=True)
class SlideLayout:
    """Binds a ``SlideType`` to a layout of the pptx template."""

    slide_type: SlideType

    # Name of the layout inside the pptx template.
    layout_name: str

    # Placeholder index on a slide created from the layout -> ``Slide`` field name.
    # Beware: a layout and a slide created from it do not hold the same shapes,
    # so these indices only make sense once the slide exists. ``check_template``
    # verifies them.
    shape_index_to_field: dict[int, str]

    # How this layout is described to the model.
    prompt: str


@dataclass(frozen=True)
class PresentationTemplate:
    """A pptx template file plus the layouts usable within it."""

    path: Path
    layouts: tuple[SlideLayout, ...]

    def get_layout(self, slide_type: SlideType) -> SlideLayout | None:
        """Return the layout bound to ``slide_type``, or None if unbound."""
        for layout in self.layouts:
            if layout.slide_type == slide_type:
                return layout
        return None
