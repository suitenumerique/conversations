"""Build a deck out of the user's own slides, so that it keeps their design.

Each slide of the new deck is a copy of one of the user's slides, whose text
shapes and tables get new Markdown texts; everything else on the slide (master,
layout, pictures, charts) is kept as it is. The user's slides that are not
copied are dropped.
"""

import copy
from dataclasses import dataclass
from io import BytesIO

import pptx
from pptx.enum.dml import MSO_COLOR_TYPE
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.shapes.base import BaseShape

from chat.file_generation.entities import PresentationStyle, TemplatedPresentation
from chat.file_generation.renderer import render, render_into_table
from chat.file_generation.styling import TITLE_FIELD, apply_text_style

MAX_TEXT_SHOWN = 300
# Attributes in this namespace hold relationship ids, e.g. r:embed on a picture.
RELATIONSHIP_ATTRIBUTE = qn("r:id").removesuffix("id")


@dataclass(frozen=True)
class TemplateOutline:
    """What the presentation agent needs to know of the user's deck."""

    # The ids of the text shapes and tables of each slide, to check the agent's answer.
    shape_ids: tuple[frozenset[int], ...]
    # The numbers of the slides holding a chart, which copies keep as it is.
    chart_slides: frozenset[int]
    # The slides described for the agent's prompt.
    description: str

    def check(self, presentation: TemplatedPresentation) -> str | None:
        """Explain how a deck does not fit the user's slides, if it does not."""
        for number, slide in enumerate(presentation.slides, start=1):
            if not 1 <= slide.template_slide <= len(self.shape_ids):
                return f"Slide {number} copies slide {slide.template_slide}, which does not exist."
            shape_ids = self.shape_ids[slide.template_slide - 1]
            if unknown := set(slide.texts) - shape_ids:
                return (
                    f"Slide {number} gives texts to shapes {sorted(unknown)}, which slide "
                    f"{slide.template_slide} does not have."
                )
            if missing := shape_ids - set(slide.texts):
                return (
                    f"Slide {number} gives no text to shapes {sorted(missing)}: give each "
                    "shape a text, its current one to keep it or an empty one to clear it."
                )
        return None

    def copied_charts(self, presentation: TemplatedPresentation) -> list[int]:
        """The numbers of the deck's slides that copy a chart with its original data."""
        return [
            number
            for number, slide in enumerate(presentation.slides, start=1)
            if slide.template_slide in self.chart_slides
        ]


def outline_template(blob: bytes) -> TemplateOutline:
    """Describe the user's slides: their text shapes, current texts and other content."""
    deck = pptx.Presentation(BytesIO(blob))
    shape_ids, chart_slides, lines = [], set(), []
    for number, slide in enumerate(deck.slides, start=1):
        shapes = _text_shapes(slide.shapes)
        shape_ids.append(frozenset(shape.shape_id for shape in shapes))
        lines.append(f"Slide {number}, layout {slide.slide_layout.name!r}:")
        for shape in shapes:
            text = _shape_text(shape)[:MAX_TEXT_SHOWN]
            lines.append(f"- shape {shape.shape_id} ({_shape_kind(shape)}): {text!r}")
        if pictures_and_charts := sorted(
            {_non_text_content(shape) for shape in slide.shapes} - {None}
        ):
            lines.append(f"- also holds: {', '.join(pictures_and_charts)}")
        if "chart" in pictures_and_charts:
            chart_slides.add(number)
    return TemplateOutline(
        shape_ids=tuple(shape_ids),
        chart_slides=frozenset(chart_slides),
        description="\n".join(lines),
    )


def build_from_template(
    blob: bytes, presentation: TemplatedPresentation, style: PresentationStyle
) -> bytes:
    """Render a deck made of copies of the user's slides into the bytes of a pptx file."""
    deck = pptx.Presentation(BytesIO(blob))
    template_slides = list(deck.slides)
    template_slide_ids = list(deck.slides._sldIdLst)  # noqa: SLF001 # pylint: disable=protected-access

    for templated in presentation.slides:
        slide = _copy_slide(deck, template_slides[templated.template_slide - 1])
        for shape in _text_shapes(slide.shapes):
            text = templated.texts.get(shape.shape_id)
            if text is None:
                continue
            if shape.has_table:
                render_into_table(shape.table, text)
            else:
                field = TITLE_FIELD if _is_title(shape) else "text"
                look = _shape_look(shape, field)
                apply_text_style(render(shape, text), field, look.updated_with(style))
        if templated.slide_notes:
            render(slide.notes_slide.notes_text_frame, templated.slide_notes)

    for slide_id in template_slide_ids:
        deck.slides._sldIdLst.remove(slide_id)  # noqa: SLF001 # pylint: disable=protected-access
        deck.part.drop_rel(slide_id.rId)

    output = BytesIO()
    deck.save(output)
    return output.getvalue()


def _copy_slide(deck, source):
    """Append a copy of a slide, with its shapes, background and the parts they use."""
    slide = deck.slides.add_slide(source.slide_layout)
    for shape in list(slide.shapes):
        shape._element.getparent().remove(shape._element)  # noqa: SLF001 # pylint: disable=protected-access

    # Pictures and charts point to other parts through relationships: relate
    # the copy to the same parts, under the ids it gives them.
    new_ids = {
        rel.rId: slide.part.relate_to(
            rel.target_ref if rel.is_external else rel.target_part,
            rel.reltype,
            is_external=rel.is_external,
        )
        for rel in source.part.rels.values()
        if rel.reltype not in (RT.SLIDE_LAYOUT, RT.NOTES_SLIDE)
    }
    for source_element in source.shapes._spTree.iter_shape_elms():  # noqa: SLF001 # pylint: disable=protected-access
        element = copy.deepcopy(source_element)
        for node in element.iter():
            for name, value in node.attrib.items():
                if name.startswith(RELATIONSHIP_ATTRIBUTE) and value in new_ids:
                    node.set(name, new_ids[value])
        slide.shapes._spTree.append(element)  # noqa: SLF001 # pylint: disable=protected-access

    if not source.follow_master_background:
        slide._element.cSld.insert(0, copy.deepcopy(source._element.cSld.bg))  # noqa: SLF001 # pylint: disable=protected-access
    return slide


def _text_shapes(shapes) -> list[BaseShape]:
    """The shapes holding text or a table, inside groups too, in reading order."""
    found = []
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            found += _text_shapes(shape.shapes)
        elif shape.has_text_frame or shape.has_table:
            found.append(shape)
    return found


def _shape_text(shape: BaseShape) -> str:
    """The text of a shape, a table being written as a Markdown table."""
    if not shape.has_table:
        return shape.text_frame.text
    rows = ["| " + " | ".join(cell.text for cell in row.cells) + " |" for row in shape.table.rows]
    separator = "|" + "---|" * len(shape.table.columns)
    return "\n".join([rows[0], separator, *rows[1:]])


def _is_title(shape: BaseShape) -> bool:
    return shape.is_placeholder and shape.placeholder_format.type in (
        PP_PLACEHOLDER.TITLE,
        PP_PLACEHOLDER.CENTER_TITLE,
    )


def _shape_kind(shape: BaseShape) -> str:
    """How a shape is described to the agent: its placeholder type, a table or a text box."""
    if shape.has_table:
        return "table"
    if shape.is_placeholder:
        return shape.placeholder_format.type.name.lower()
    return "text box"


def _non_text_content(shape: BaseShape) -> str | None:
    """The kind of content of a shape that copies keep as it is, if any."""
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        return "picture"
    if shape.has_chart:
        return "chart"
    return None


def _shape_look(shape: BaseShape, field: str) -> PresentationStyle:
    """
    The font, size and colour set on the first run of a shape, as a style for its field.

    Rendering new text drops the formatting of the runs it replaces: this keeps
    the look of a deck formatted by hand rather than through its layouts.
    """
    run = next((run for paragraph in shape.text_frame.paragraphs for run in paragraph.runs), None)
    if run is None:
        return PresentationStyle()
    prefix = "title" if field == TITLE_FIELD else "text"
    color_type = run.font.color.type
    # Built without validation: a hand-made deck may use sizes the user may not ask for.
    return PresentationStyle.model_construct(
        **{
            f"{prefix}_color": str(run.font.color.rgb)
            if color_type == MSO_COLOR_TYPE.RGB
            else None,
            f"{prefix}_font": run.font.name,
            f"{prefix}_size": run.font.size.pt if run.font.size else None,
        }
    )
