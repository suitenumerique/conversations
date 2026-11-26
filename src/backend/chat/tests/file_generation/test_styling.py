"""
Tests for the deck-wide style.

Real components: the bundled pptx template and python-pptx. Decks are built in
memory and read back to assert what a user would actually open.
"""

from io import BytesIO

import pptx
import pytest
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml.ns import qn
from pptx.util import Pt
from pydantic import ValidationError

from chat.file_generation import (
    GENERIC_TEMPLATE,
    Presentation,
    PresentationStyle,
    Slide,
    SlideType,
    build_presentation,
)
from chat.file_generation.styling import DEFAULT_TEXT_SIZE

STYLE = PresentationStyle(
    title_color="#000091",
    text_color="E1000F",
    background_color="#F5F5FE",
    title_font="Arial",
    text_font="Georgia",
    title_size=32,
    text_size=18,
)


def build_deck(slides, style=None):
    """Build a deck from slides and reopen it as python-pptx would."""
    blob = build_presentation(GENERIC_TEMPLATE, Presentation(title="Deck", slides=slides), style)
    return pptx.Presentation(BytesIO(blob))


def runs_of(shape):
    """Return the runs of a text shape, or of every cell of a table."""
    frames = (
        [shape.text_frame]
        if shape.has_text_frame
        else [cell.text_frame for cell in shape.table.iter_cells()]
    )
    return [run for frame in frames for paragraph in frame.paragraphs for run in paragraph.runs]


def content_slide(**fields):
    """A one-column slide, after the cover every deck opens with."""
    return [
        Slide(type=SlideType.COVER, title="Couverture"),
        Slide(type=SlideType.TITLE_ONE_COLUMN, title="Constats", **fields),
    ]


def font_scale(shape):
    """The shrink-to-fit scale stored on a shape, in percent, if any."""
    autofit = shape.text_frame._bodyPr.find(qn("a:normAutofit"))  # pylint: disable=protected-access
    scale = autofit.get("fontScale") if autofit is not None else None
    return int(scale) / 1000 if scale else None


def test_a_full_style_is_applied():
    """
    Titles take the title style, every other field the text style, and every
    slide the background; a font the renderer set on purpose (inline code) stays.
    """
    deck = build_deck(content_slide(content="- Premier\n- **Second**\n\nLancer `make run`"), STYLE)
    title_shape, body_shape = deck.slides[1].shapes[0], deck.slides[1].shapes[1]

    for run in runs_of(title_shape):
        assert run.font.color.rgb == RGBColor.from_string("000091")
        assert run.font.name == "Arial"
        assert run.font.size == Pt(32)
    code_run = next(run for run in runs_of(body_shape) if run.text == "make run")
    assert code_run.font.name == "Consolas"
    assert code_run.font.size == Pt(10)
    for run in runs_of(body_shape):
        assert run.font.color.rgb == RGBColor.from_string("E1000F")
        if run.text != "make run":
            assert run.font.name == "Georgia"
            assert run.font.size == Pt(18)
    for slide in deck.slides:
        assert slide.background.fill.fore_color.rgb == RGBColor.from_string("F5F5FE")


def test_cover_and_section_slides_keep_their_layout_sizes():
    """
    Cover and section slides, designed with larger text, take the colours and
    fonts but not the sizes.
    """
    deck = build_deck(
        [
            Slide(type=SlideType.COVER, title="Couverture", subtitle="Sous-titre"),
            Slide(type=SlideType.SECTION, title="Partie", subtitle="Détail"),
        ],
        STYLE,
    )

    runs = [run for slide in deck.slides for shape in slide.shapes for run in runs_of(shape)]
    assert {run.text for run in runs} == {"Couverture", "Sous-titre", "Partie", "Détail"}
    for run in runs:
        assert run.font.size is None
        assert run.font.name in ("Arial", "Georgia")
        assert run.font.color.rgb in (
            RGBColor.from_string("000091"),
            RGBColor.from_string("E1000F"),
        )


def test_tables_take_the_text_font_keep_their_colours_and_shrink():
    """
    A table takes the text font but keeps the colours designed for its cells'
    fills. It never shrinks on its own, so a long one is given a smaller size.
    """
    short = "| A | B |\n|---|---|\n| 1 | 2 |"
    long = "| A | B |\n|---|---|\n" + "\n".join(
        f"| Indicateur numéro {i} au libellé assez long | Valeur {i} |" for i in range(12)
    )

    def table_runs(content, style):
        deck = build_deck(content_slide(content=content), style)
        return runs_of(next(shape for shape in deck.slides[1].shapes if shape.has_table))

    runs = table_runs(short, STYLE)
    assert runs
    assert all(run.font.color.type is None for run in runs)
    assert all(run.font.name == "Georgia" for run in runs)
    assert {run.font.size for run in table_runs(short, PresentationStyle(text_size=16))} == {Pt(16)}
    (long_size,) = {run.font.size for run in table_runs(long, PresentationStyle(text_size=16))}
    assert Pt(8) <= long_size < Pt(16)
    # Inline code is set in a small size: the table's text is not sized after it.
    code_first = "| `id` | B |\n|---|---|\n| 1 | 2 |"
    assert {run.font.size for run in table_runs(code_first, None)} == {Pt(DEFAULT_TEXT_SIZE)}
    # Unless that is the text font: the size asked for is kept.
    consolas = PresentationStyle(text_font="Consolas", text_size=18)
    assert {run.font.size for run in table_runs(short, consolas)} == {Pt(18)}


def test_unset_fields_keep_the_template_styling():
    """
    No style sets nothing, a partial style only sets its fields, and updating a
    style keeps every field the changes leave unset.
    """
    unstyled = build_deck(content_slide(content="Corps"))
    for shape in unstyled.slides[1].shapes:
        if shape.has_text_frame:
            for run in runs_of(shape):
                assert run.font.size is None
                assert run.font.name is None
    assert unstyled.slides[1].follow_master_background

    partial = build_deck(content_slide(content="Corps"), PresentationStyle(text_size=20))
    title_shape, body_shape = partial.slides[1].shapes[0], partial.slides[1].shapes[1]
    assert all(run.font.size is None for run in runs_of(title_shape))
    assert all(run.font.size == Pt(20) for run in runs_of(body_shape))
    assert all(run.font.name is None for run in runs_of(body_shape))

    current = PresentationStyle(title_color="#000091", text_size=14)
    updated = current.updated_with(PresentationStyle(text_size=20, text_font="Arial"))
    assert updated == PresentationStyle(title_color="#000091", text_size=20, text_font="Arial")


@pytest.mark.parametrize(
    "field,value",
    [
        ("title_color", "blue"),
        ("text_color", "#12345"),
        ("title_size", 200),
        ("text_size", 2),
        ("text_font", "x" * 65),
        ("title_font", "Ari\x01al"),
    ],
)
def test_invalid_style_values_are_rejected(field, value):
    """Colours must be hex codes, sizes and font names stay in sane bounds."""
    with pytest.raises(ValidationError):
        PresentationStyle(**{field: value})


def test_text_shrinks_to_fit_its_shape():
    """
    Titles and text are set to shrink to fit, with or without a style. Overflowing
    text also stores a shrink scale, which PowerPoint applies on opening; text
    that fits keeps its size.
    """
    long_text = "\n".join(
        f"- Une puce assez longue pour occuper toute une ligne, numéro {i}" for i in range(15)
    )
    overflowing = build_deck(content_slide(content=long_text), PresentationStyle(text_size=20))
    fitting = build_deck(content_slide(content="- Court\n- Bref"), PresentationStyle(text_size=20))

    scale = font_scale(overflowing.slides[1].shapes[1])
    assert scale is not None
    assert 50 <= scale < 100
    assert font_scale(fitting.slides[1].shapes[1]) is None
    unstyled = build_deck(content_slide(content="- Court\n- Bref"))
    for shape in list(unstyled.slides[1].shapes)[:2]:
        assert shape.text_frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
