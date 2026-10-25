"""Assemble a pptx deck from a validated presentation spec."""

import logging
from io import BytesIO

import pptx
from pptx.enum.shapes import MSO_SHAPE_TYPE

from chat.file_generation.entities import (
    Presentation,
    PresentationStyle,
    PresentationTemplate,
    Slide,
    SlideLayout,
    SlideType,
)
from chat.file_generation.renderer import render
from chat.file_generation.styling import apply_background, apply_text_style

logger = logging.getLogger(__name__)

# SHA1 of the template's bundled "insert image" placeholder graphic
# (ppt/media/image1.png, a 128x72 mountain icon baked as a real picture into the
# cover layouts). Matched by content so a genuine logo added later is left alone.
_PLACEHOLDER_IMAGE_SHA1 = "040bc0d66044b02fb0265ed1bc6a912f3a109c54"


class PresentationBuildError(Exception):
    """Raised when a deck cannot be assembled from its template."""


def build_presentation(
    template: PresentationTemplate,
    presentation: Presentation,
    style: PresentationStyle | None = None,
) -> bytes:
    """Render a presentation spec into the bytes of a pptx file, with an optional style."""
    style = style or PresentationStyle()
    try:
        deck = pptx.Presentation(str(template.path))
    except Exception as exc:
        logger.exception("Failed to open presentation template %s", template.path)
        raise PresentationBuildError(
            f"Could not open the presentation template at {template.path}."
        ) from exc

    _strip_placeholder_pictures(deck)

    for slide in presentation.slides:
        layout = template.get_layout(slide.type)
        if layout is None:
            # Unreachable for shipped types: the spec is validated against
            # SlideType and every member is bound (test_every_slide_type_...).
            # Guards a new type added without a binding.
            raise PresentationBuildError(f"No layout is bound to slide type {slide.type!r}.")
        _add_slide(deck, layout, slide, style)

    blob = BytesIO()
    deck.save(blob)
    return blob.getvalue()


def _strip_placeholder_pictures(deck) -> None:
    """Remove the template's dummy 'insert image' graphic from its master and layouts.

    The bundled template bakes a placeholder picture into its master and cover
    layouts as a real picture, so it renders through onto generated slides. Drop
    it from the in-memory deck; the template file on disk is untouched.
    """
    for master_or_layout in [*deck.slide_masters, *deck.slide_layouts]:
        for shape in list(master_or_layout.shapes):
            if (
                shape.shape_type == MSO_SHAPE_TYPE.PICTURE
                and shape.image.sha1 == _PLACEHOLDER_IMAGE_SHA1
            ):
                shape._element.getparent().remove(shape._element)  # noqa: SLF001 # pylint: disable=protected-access


def _add_slide(deck, layout: SlideLayout, slide: Slide, style: PresentationStyle) -> None:
    """Create a slide from its layout, fill the mapped placeholders and style them."""
    pptx_layout = deck.slide_layouts.get_by_name(layout.layout_name)
    if pptx_layout is None:
        raise PresentationBuildError(
            f"Layout {layout.layout_name!r} is missing from the presentation template."
        )

    if slide.type in (SlideType.COVER, SlideType.SECTION):
        # Designed with larger text than content slides: they keep their layout's sizes.
        style = style.model_copy(update={"title_size": None, "text_size": None})

    pptx_slide = deck.slides.add_slide(pptx_layout)
    apply_background(pptx_slide, style)
    for shape_index, field in layout.shape_index_to_field.items():
        rendered = render(pptx_slide.shapes[shape_index], getattr(slide, field, ""))
        apply_text_style(rendered, field, style)
    _remove_empty_placeholders(pptx_slide)

    if slide.slide_notes:
        render(pptx_slide.notes_slide.notes_text_frame, slide.slide_notes)


def _remove_empty_placeholders(pptx_slide) -> None:
    """Drop the placeholders left empty, which PowerPoint shows as prompts when editing."""
    for placeholder in list(pptx_slide.placeholders):
        if placeholder.has_table or (
            placeholder.has_text_frame and placeholder.text_frame.text.strip()
        ):
            continue
        placeholder._element.getparent().remove(placeholder._element)  # noqa: SLF001 # pylint: disable=protected-access


def check_template(template: PresentationTemplate) -> None:
    """
    Assert a template is consistent with the layouts declared against it.

    Called from the tests rather than at import time: it opens the file and
    builds a throwaway slide per layout, which is too costly to pay on every
    worker start.
    """
    deck = pptx.Presentation(str(template.path))
    layout_names = [layout.name for layout in deck.slide_layouts]

    for layout in template.layouts:
        pptx_layout = deck.slide_layouts.get_by_name(layout.layout_name)
        if pptx_layout is None:
            raise PresentationBuildError(
                f"Layout {layout.layout_name!r} not found in {template.path}. "
                f"Available layouts: {layout_names}"
            )

        # A layout and a slide created from it do not carry the same shapes, so
        # the declared indices can only be checked against a real slide.
        pptx_slide = deck.slides.add_slide(pptx_layout)
        shape_count = len(pptx_slide.shapes)
        if layout.shape_index_to_field and max(layout.shape_index_to_field) >= shape_count:
            raise PresentationBuildError(
                f"Layout {layout.layout_name!r} has {shape_count} shapes, but a "
                f"placeholder index {max(layout.shape_index_to_field)} is declared."
            )
