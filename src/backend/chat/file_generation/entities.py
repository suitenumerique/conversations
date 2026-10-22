"""Data structures describing a presentation and the template that renders it."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="after")
    def check_cover_first(self):
        """The deck must open with a ``cover`` slide."""
        if self.slides[0].type != SlideType.COVER:
            raise ValueError("The first slide must be a cover slide.")
        return self


class TemplatedSlide(BaseModel):
    """A slide copied from one of the user's own slides, with new texts."""

    template_slide: int = Field(description="Number of the user's slide to copy, from 1")
    texts: dict[int, str] = Field(
        default_factory=dict,
        description="New Markdown text of the copied slide's text shapes, by shape id",
    )
    slide_notes: str = ""


class TemplatedPresentation(BaseModel):
    """A whole deck built out of the user's own slides."""

    title: str
    slides: list[TemplatedSlide] = Field(min_length=1)


HexColor = Annotated[
    str, Field(pattern=r"^#?[0-9A-Fa-f]{6}$", description="Hex colour, e.g. #000091")
]
FontName = Annotated[
    str,
    Field(
        max_length=64,
        description="Font family, shown only if installed where the deck is opened",
    ),
]


class PresentationStyle(BaseModel):
    """
    Deck-wide style applied over the template's own.

    Every field is optional: an unset one leaves the template's styling in place.
    Titles are the ``title`` field of each slide; text is every other field.
    """

    title_color: HexColor | None = None
    text_color: HexColor | None = None
    background_color: HexColor | None = None
    title_font: FontName | None = None
    text_font: FontName | None = None
    title_size: float | None = Field(default=None, ge=10, le=96, description="In points")
    text_size: float | None = Field(default=None, ge=8, le=60, description="In points")

    def updated_with(self, changes: "PresentationStyle") -> "PresentationStyle":
        """Return this style with every field set in ``changes`` overriding it."""
        return self.model_copy(update=changes.model_dump(exclude_none=True))


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
