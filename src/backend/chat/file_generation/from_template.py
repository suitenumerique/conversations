"""Build a deck out of the user's own slides, so that it keeps their design.

Each slide of the new deck is a copy of one of the user's slides, or a new
slide made from one of their layouts, whose text shapes and tables may get new
Markdown texts; everything else on the slide (master, layout, pictures, charts,
the shapes given no text) is kept as it is. The user's slides that are not
copied are dropped.
"""

import copy
import json
import re
from collections import Counter
from dataclasses import dataclass
from io import BytesIO

import pptx
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.oxml import serialize_part_xml
from pptx.opc.package import PartFactory, XmlPart
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.shapes.base import BaseShape

from chat.file_generation.entities import PresentationStyle, TemplatedPresentation
from chat.file_generation.renderer import (
    HYPERLINKS,
    MONO_FONT,
    merge_run_properties,
    render,
    render_into_table,
)
from chat.file_generation.styling import (
    TITLE_FIELD,
    apply_background,
    apply_text_style,
    text_style_of,
)

# Attributes in this namespace hold relationship ids, e.g. r:embed on a picture.
RELATIONSHIP_ATTRIBUTE = qn("r:id").removesuffix("id")
# What a copy must not bring along: links to other slides, which would keep the
# slides the deck drops inside its file, and review comments, legacy and modern.
NOT_COPIED = (
    RT.SLIDE,
    RT.COMMENTS,
    "http://schemas.microsoft.com/office/2018/10/relationships/comments",
)
# What each copy gets its own copy of: PowerPoint asks to repair a deck whose
# slides share a chart or a SmartArt, then blanks one of them. Pictures stay shared.
OWN_COPY = (
    RT.CHART,
    RT.CHART_COLOR_STYLE,
    "http://schemas.microsoft.com/office/2011/relationships/chartStyle",
    RT.CHART_USER_SHAPES,
    RT.PACKAGE,  # The workbook holding a chart's data.
    RT.THEME_OVERRIDE,
    RT.DIAGRAM_COLORS,
    RT.DIAGRAM_DATA,
    RT.DIAGRAM_LAYOUT,
    RT.DIAGRAM_QUICK_STYLE,
    "http://schemas.microsoft.com/office/2007/relationships/diagramDrawing",
)
# The most the copies of those parts may weigh in a deck: a chart's workbook,
# or an embedded file, can weigh megabytes and be copied on 50 slides.
MAX_COPIED_SIZE = 50 * 2**20
# What the deck keeps of the user's file, at the file and presentation levels.
# Anything else, such as the thumbnail, custom properties and data, comment
# authors, co-authoring history or tags, can name people or describe the
# dropped slides: it is left out, as is any kind of part not listed here.
KEPT_FILE_PARTS = (RT.OFFICE_DOCUMENT, RT.CORE_PROPERTIES, RT.EXTENDED_PROPERTIES)
KEPT_PRESENTATION_PARTS = (
    RT.SLIDE_MASTER,
    RT.NOTES_MASTER,
    RT.HANDOUT_MASTER,
    RT.SLIDE,
    RT.THEME,
    RT.PRES_PROPS,
    RT.VIEW_PROPS,
    RT.TABLE_STYLES,
    RT.FONT,
)
# Content PowerPoint wraps for older readers (equations, 3D models, zooms):
# copies leave it out, as it may point to the slides the deck drops.
ALTERNATE_CONTENT = "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"
EMPTY_EXTENDED_PROPERTIES = (
    b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n<Properties "
    b'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"/>'
)
# The extension of presentation.xml that groups its slides into sections.
SECTIONS_EXTENSION = "{521415D9-36F7-43E2-AB2F-B90AF26B5E84}"
# Placeholders that only take a picture, chart, table or media, never text.
CONTENT_SLOTS = (
    PP_PLACEHOLDER.BITMAP,
    PP_PLACEHOLDER.CHART,
    PP_PLACEHOLDER.MEDIA_CLIP,
    PP_PLACEHOLDER.ORG_CHART,
    PP_PLACEHOLDER.PICTURE,
    PP_PLACEHOLDER.TABLE,
)
# Paragraph properties that make a paragraph a bulleted or numbered list item.
LIST_MARKERS = (qn("a:buAutoNum"), qn("a:buChar"))
# The number the renderer writes as text at the start of a numbered list item.
RENDERED_NUMBER = re.compile(r"\d+\. ")


class TemplateTooLargeError(ValueError):
    """The deck would hold too many copies of heavy charts or embedded files."""


@dataclass(frozen=True)
class TemplateOutline:
    """What the presentation agent needs to know of the user's deck."""

    # The ids of the text shapes and tables of each slide, to check the agent's answer.
    shape_ids: tuple[frozenset[int], ...]
    # The ids of the placeholders of a new slide made from each layout, by layout name.
    layout_shape_ids: dict[str, frozenset[int]]
    # The slides and layouts described for the agent's prompt.
    description: str

    def check(self, presentation: TemplatedPresentation) -> str | None:
        """Explain how a deck does not fit the user's slides, if it does not."""
        copies = Counter(slide.template_slide for slide in presentation.slides)
        for number, slide in enumerate(presentation.slides, start=1):
            if bool(slide.layout) == (slide.template_slide is not None):
                return (
                    f"Slide {number} must either copy one of the user's slides, in "
                    "`template_slide`, or be made from one of their layouts, in `layout`."
                )
            if slide.layout:
                if slide.layout not in self.layout_shape_ids:
                    return f"Slide {number} uses layout {slide.layout!r}, which does not exist."
                shape_ids, source = self.layout_shape_ids[slide.layout], f"layout {slide.layout!r}"
            elif slide.template_slide and 1 <= slide.template_slide <= len(self.shape_ids):
                shape_ids = self.shape_ids[slide.template_slide - 1]
                source = f"slide {slide.template_slide}"
            else:
                return f"Slide {number} copies slide {slide.template_slide}, which does not exist."
            if unknown := set(slide.texts) - shape_ids:
                return (
                    f"Slide {number} gives texts to shapes {sorted(unknown)}, which {source} "
                    f"does not have: its shapes are {sorted(shape_ids)}."
                )
            copied_again = not slide.layout and copies[slide.template_slide] > 1
            if copied_again and (missing := shape_ids - set(slide.texts)):
                return (
                    f"Slide {number} copies slide {slide.template_slide}, which is copied several "
                    f"times, but gives no text to shapes {sorted(missing)}: give each copy a text "
                    "for every shape, an empty one to remove it."
                )
        return None


def outline_template(blob: bytes) -> TemplateOutline:
    """Describe the user's slides: their text shapes, current texts and other content."""
    deck = pptx.Presentation(BytesIO(blob))
    shape_ids, lines = [], []
    for number, slide in enumerate(deck.slides, start=1):
        shapes = _text_shapes(slide.shapes)
        shape_ids.append(frozenset(shape.shape_id for shape in shapes))
        hidden = " (hidden)" if _is_hidden(slide) else ""
        lines.append(f"Slide {number}{hidden}, layout {slide.slide_layout.name!r}:")
        for shape in shapes:
            # As JSON, which keeps characters like non-breaking spaces as they are.
            text = json.dumps(_shape_text(shape), ensure_ascii=False)
            lines.append(f"- {_describe(shape)}: {text}")
        notes = slide.notes_slide.notes_text_frame if slide.has_notes_slide else None
        if notes is not None and notes.text.strip():
            lines.append(f"- speaker notes: {json.dumps(notes.text, ensure_ascii=False)}")
        if pictures_and_charts := sorted(
            {_non_text_content(shape) for shape in slide.shapes} - {None}
        ):
            lines.append(f"- also holds: {', '.join(pictures_and_charts)}")
        if slide.shapes._spTree.find(ALTERNATE_CONTENT) is not None:  # noqa: SLF001 # pylint: disable=protected-access
            lines.append("- also holds: content that copies leave out")

    layout_shape_ids = {}
    for name, layout in _layouts(deck).items():
        if shapes := _text_shapes(deck.slides.add_slide(layout).shapes):
            layout_shape_ids[name] = frozenset(shape.shape_id for shape in shapes)
            lines.append(f"Layout {name!r}:")
            lines += [f"- {_describe(shape)}" for shape in shapes]
    return TemplateOutline(
        shape_ids=tuple(shape_ids),
        layout_shape_ids=layout_shape_ids,
        description="\n".join(lines),
    )


def build_from_template(
    blob: bytes, presentation: TemplatedPresentation, style: PresentationStyle
) -> bytes:
    """Render a deck made of copies of the user's slides into the bytes of a pptx file."""
    deck = pptx.Presentation(BytesIO(blob))
    template_slides = list(deck.slides)
    template_slide_ids = list(deck.slides._sldIdLst)  # noqa: SLF001 # pylint: disable=protected-access
    # Before copying anything: a too heavy deck would be built in memory first.
    copied_size = sum(
        _copied_size(template_slides[templated.template_slide - 1].part)
        for templated in presentation.slides
        if not templated.layout
    )
    if copied_size > MAX_COPIED_SIZE:
        raise TemplateTooLargeError

    for templated in presentation.slides:
        if templated.layout:
            slide = deck.slides.add_slide(_layouts(deck)[templated.layout])
        else:
            slide = _copy_slide(deck, template_slides[templated.template_slide - 1])
        apply_background(slide, style)
        for shape in _text_shapes(slide.shapes):
            _fill_shape(shape, templated.texts.get(shape.shape_id), style)
        # A notes page has no text frame when the user's notes master has no body placeholder.
        notes = slide.notes_slide.notes_text_frame if templated.slide_notes else None
        if notes is not None:
            render(notes, templated.slide_notes)

    # Before dropping the user's slides: a custom show also relates to them.
    _drop_slide_lists(deck)
    for slide_id in template_slide_ids:
        deck.slides._sldIdLst.remove(slide_id)  # noqa: SLF001 # pylint: disable=protected-access
        deck.part.drop_rel(slide_id.rId)
    _clear_metadata(deck, presentation.title)
    _drop_links_to_what_is_left_out(deck, {slide.part for slide in template_slides})

    output = BytesIO()
    deck.save(output)
    return output.getvalue()


def _fill_shape(shape: BaseShape, text: str | None, style: PresentationStyle) -> None:
    """Give a copied shape its new text, if any, and the style the user asked for."""
    if text == "":
        # Before comparing texts: a shape holding none, a filled tile, is removed too.
        shape._element.getparent().remove(shape._element)  # noqa: SLF001 # pylint: disable=protected-access
        return
    if text is not None and _words(text) != _words(_shape_text(shape)):
        if not shape.has_table:
            _render_text(shape, text, style)
            return
        render_into_table(shape.table, text)
    # A shape keeping its text, or a table, keeps its own looks but for the
    # style fields the user set: a restyled deck must change everywhere. It is
    # fitted again only to a new size, or a text box to a new font: fitting a
    # table gives all its cells one size.
    field = TITLE_FIELD if _is_title(shape) else "text"
    color, font, size = text_style_of(style, field)
    if color or font or size:
        apply_text_style(shape, field, style, fit=bool(size or (font and not shape.has_table)))


def _words(text: str) -> list[list[str]]:
    """The words of each paragraph of a text, whatever its spacing and blank lines."""
    return [line.split() for line in text.splitlines() if line.strip()]


def _render_text(shape: BaseShape, text: str, style: PresentationStyle) -> None:
    """Write new Markdown into a text shape, keeping its looks, or put a table in its place."""
    looks = _looks(shape)
    content = render(shape, text)
    if content is shape:
        _restore_looks(shape, looks)
    else:
        # A Markdown table takes the shape's place, inside its group if it is in
        # one: the table was given the shape's coordinates, which are the group's.
        shape._element.addprevious(content._element)  # noqa: SLF001 # pylint: disable=protected-access
        shape._element.getparent().remove(shape._element)  # noqa: SLF001 # pylint: disable=protected-access
    apply_text_style(content, TITLE_FIELD if _is_title(shape) else "text", style)


def _clear_metadata(deck, title: str) -> None:
    """
    Leave out of the deck what the user's file says of who wrote it and of the
    slides it dropped: its authors, the application properties, which list the
    slide titles and the company, and every part the deck does not need.
    """
    properties = deck.core_properties
    for name in (
        "author",
        "category",
        "comments",
        "content_status",
        "identifier",
        "keywords",
        "last_modified_by",
        "subject",
        "version",
    ):
        setattr(properties, name, "")
    properties.title = title[:255]

    # pylint: disable=protected-access
    package = deck.part.package
    for rels, kept in ((package._rels, KEPT_FILE_PARTS), (deck.part.rels, KEPT_PRESENTATION_PARTS)):  # noqa: SLF001
        for rel in list(rels.values()):
            if rel.reltype not in kept:
                rels.pop(rel.rId)
            elif rel.reltype == RT.EXTENDED_PROPERTIES:
                # PowerPoint writes them again on save.
                rel.target_part._blob = EMPTY_EXTENDED_PROPERTIES  # noqa: SLF001


def _drop_links_to_what_is_left_out(deck, dropped: set) -> None:
    """
    Remove, from every part the deck keeps, its links to the dropped slides, such
    as the outline view's list of collapsed slides, which would keep them in the
    file, and every link to a part no longer related, which PowerPoint repairs.
    """
    # pylint: disable=protected-access
    for part in list(deck.part.package.iter_parts()):
        if part in dropped:
            continue
        rels = part.rels
        for rel in list(rels.values()):
            if not rel.is_external and rel.target_part in dropped:
                rels.pop(rel.rId)
        if isinstance(part, XmlPart):
            _drop_links(part._element, set(rels))  # noqa: SLF001
        elif part.content_type.endswith("xml"):
            # A part python-pptx does not parse, such as the view properties.
            element = parse_xml(part.blob)
            if _drop_links(element, set(rels)):
                part._blob = serialize_part_xml(element)  # noqa: SLF001


def _drop_links(element, rel_ids: set[str]) -> bool:
    """Remove the nodes of an element linking to none of ``rel_ids``, telling if any was."""
    dangling = {
        value
        for node in element.iter()
        for name, value in node.attrib.items()
        # An empty id is no link: an action such as "next slide" has one.
        if name.startswith(RELATIONSHIP_ATTRIBUTE) and value and value not in rel_ids
    }
    _relink(element, {}, dangling)
    return bool(dangling)


def _drop_slide_lists(deck) -> None:
    """
    Drop the sections and custom shows of the user's deck. They list its slides,
    not the copies, and PowerPoint asks to repair a file whose lists do not match
    its slides; the copies may come in any order, so they cannot be mapped back.
    """
    presentation = deck.part._element  # noqa: SLF001 # pylint: disable=protected-access
    if (custom_shows := presentation.find(qn("p:custShowLst"))) is not None:
        presentation.remove(custom_shows)
    if (extensions := presentation.find(qn("p:extLst"))) is not None:
        for extension in extensions.findall(qn("p:ext")):
            if extension.get("uri") == SECTIONS_EXTENSION:
                extensions.remove(extension)
        if len(extensions) == 0:  # An lxml element is falsy when it has no children.
            presentation.remove(extensions)


def _copy_slide(deck, source):
    """
    Append a copy of a slide, with its shapes, background, hidden flag and the
    parts they use, and the colour-map override that sets which theme colours
    they show. Its transition and animations are left out: animations point to
    shapes by id, which the copy may remove.
    """
    slide = deck.slides.add_slide(source.slide_layout)
    if _is_hidden(source):
        slide._element.set("show", "0")  # noqa: SLF001 # pylint: disable=protected-access
    color_map = qn("p:clrMapOvr")
    if (own := slide._element.find(color_map)) is not None:  # noqa: SLF001 # pylint: disable=protected-access
        slide._element.remove(own)  # noqa: SLF001 # pylint: disable=protected-access
    if (override := source._element.find(color_map)) is not None:  # noqa: SLF001 # pylint: disable=protected-access
        slide._element.cSld.addnext(copy.deepcopy(override))  # noqa: SLF001 # pylint: disable=protected-access
    for shape in list(slide.shapes):
        shape._element.getparent().remove(shape._element)  # noqa: SLF001 # pylint: disable=protected-access

    new_ids, dropped_ids = _relate_like(source.part, slide.part, (RT.SLIDE_LAYOUT, RT.NOTES_SLIDE))
    for source_element in source.shapes._spTree.iter_shape_elms():  # noqa: SLF001 # pylint: disable=protected-access
        slide.shapes._spTree.append(_relinked(source_element, new_ids, dropped_ids))  # noqa: SLF001 # pylint: disable=protected-access

    if not source.follow_master_background:
        # A picture background points to its image through a relationship too.
        background = _relinked(source._element.cSld.bg, new_ids, dropped_ids)  # noqa: SLF001 # pylint: disable=protected-access
        slide._element.cSld.insert(0, background)  # noqa: SLF001 # pylint: disable=protected-access

    _copy_notes(source, slide)
    return slide


def _is_hidden(slide) -> bool:
    """Whether a slide is left out of the slideshow, its flag being a boolean."""
    return slide._element.get("show") in ("0", "false")  # noqa: SLF001 # pylint: disable=protected-access


def _relate_like(source, target, skipped=()) -> tuple[dict[str, str], set[str]]:
    """
    Relate a copied part to what its source points to (pictures, charts...),
    returning the ids the copy gives them and the ids of what is not copied.
    """
    new_ids = {}
    for rel in source.rels.values():
        if rel.reltype in (*skipped, *NOT_COPIED):
            continue
        if rel.is_external:
            new_ids[rel.rId] = target.relate_to(rel.target_ref, rel.reltype, is_external=True)
        elif rel.reltype in OWN_COPY:
            new_ids[rel.rId] = _relate_to_copy(target, rel.target_part, rel.reltype)
        else:
            new_ids[rel.rId] = target.relate_to(rel.target_part, rel.reltype)
    dropped_ids = {rel.rId for rel in source.rels.values() if rel.reltype in NOT_COPIED}
    return new_ids, dropped_ids


def _copied_size(part) -> int:
    """The size of the parts a copy of a part gets its own copies of."""
    return sum(
        len(rel.target_part.blob) + _copied_size(rel.target_part)
        for rel in part.rels.values()
        if not rel.is_external and rel.reltype in OWN_COPY
    )


def _relate_to_copy(owner, part, reltype: str) -> str:
    """Relate a part to a copy of another one, under a new name, with copies of its own parts."""
    package = part.package
    # E.g. "/ppt/charts/chart1.xml" is numbered as "/ppt/charts/chart%d.xml".
    template = re.sub(r"\d*(\.\w+)$", r"%d\1", part.partname.replace("%", "%%"))
    clone = PartFactory(package.next_partname(template), part.content_type, package, part.blob)
    # Related first, so that the names given to its own parts see it in the package.
    rel_id = owner.relate_to(clone, reltype)
    new_ids, dropped_ids = _relate_like(part, clone)
    if isinstance(clone, XmlPart):
        clone._element = _relinked(clone._element, new_ids, dropped_ids)  # noqa: SLF001 # pylint: disable=protected-access
    return rel_id


def _copy_notes(source, slide) -> None:
    """Give a copy the speaker notes of its slide, which new ``slide_notes`` replace."""
    notes = source.notes_slide.notes_text_frame if source.has_notes_slide else None
    if notes is None or not notes.text.strip():
        return
    target = slide.notes_slide.notes_text_frame
    if target is None:
        return
    # The links of the notes go through the notes' own relationships, not copied.
    body = _relinked(notes._txBody, {}, set(source.notes_slide.part.rels))  # noqa: SLF001 # pylint: disable=protected-access
    target._txBody.getparent().replace(target._txBody, body)  # noqa: SLF001 # pylint: disable=protected-access


def _relinked(source_element, new_ids: dict[str, str], dropped_ids: set[str]):
    """
    Copy an element of a slide, pointing its relationship ids to the copy's own,
    and removing the nodes that link to what is not copied.
    """
    element = copy.deepcopy(source_element)
    _relink(element, new_ids, dropped_ids)
    return element


def _relink(element, new_ids: dict[str, str], dropped_ids: set[str]) -> None:
    """Point an element's relationship ids to new ones, removing nodes linking to dropped ones."""
    for node in list(element.iter()):
        for name, value in list(node.attrib.items()):
            if not name.startswith(RELATIONSHIP_ATTRIBUTE):
                continue
            if value in dropped_ids:  # E.g. a link to another slide, gone with it.
                node.getparent().remove(node)
                break
            if value in new_ids:
                node.set(name, new_ids[value])


def _layouts(deck) -> dict:
    """The layouts of every master of a deck, by name, the first one winning."""
    layouts = {}
    for master in deck.slide_masters:
        for layout in master.slide_layouts:
            layouts.setdefault(layout.name, layout)
    return layouts


def _text_shapes(shapes) -> list[BaseShape]:
    """The shapes holding text or a table, inside groups too, in reading order."""
    found = []
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            found += _text_shapes(shape.shapes)
        elif (
            shape.is_placeholder
            and shape.placeholder_format.type in CONTENT_SLOTS
            and not shape.has_table  # A table put in its slot stays a placeholder.
        ):
            continue  # An empty slot for a picture, chart or table: text cannot go there.
        elif shape.has_text_frame or shape.has_table:
            found.append(shape)
    return found


def _shape_text(shape: BaseShape) -> str:
    """The text of a shape, a table being written as a Markdown table."""
    if not shape.has_table:
        return shape.text_frame.text
    # A pipe inside a cell is escaped, or it would read as the end of the cell.
    rows = [
        "| "
        + " | ".join(cell.text.replace("|", "\\|").replace("\n", "<br>") for cell in row.cells)
        + " |"
        for row in shape.table.rows
    ]
    separator = "|" + "---|" * len(shape.table.columns)
    return "\n".join([rows[0], separator, *rows[1:]])


def _looks(shape: BaseShape) -> dict:
    """
    The properties of the first paragraph and run of each level of a shape, or of
    its layout's sample title when it is an empty title, for its new text to take.
    """
    if shape.text_frame.text.strip():
        source = shape
    else:  # The sample text of a body is filler, often in bold: only a title's is a look.
        source = _layout_sample(shape) if _is_title(shape) else None
    looks = {}
    for paragraph in source.text_frame.paragraphs if source else []:
        if paragraph.level in looks or not paragraph.runs:
            continue
        all_properties = [run._r.get_or_add_rPr() for run in paragraph.runs]  # noqa: SLF001 # pylint: disable=protected-access
        run_properties = copy.deepcopy(all_properties[0])
        # Emphasis is the paragraph's look only when all its runs share it, not a bold label.
        for emphasis in ("b", "i", "u"):
            if len({properties.get(emphasis) for properties in all_properties}) > 1:
                run_properties.attrib.pop(emphasis, None)
        # A link belongs to the text it was on, not to the look the new text takes.
        for link in [*run_properties.iterchildren(*HYPERLINKS)]:
            run_properties.remove(link)
        looks[paragraph.level] = (copy.deepcopy(paragraph._p.pPr), run_properties)  # noqa: SLF001 # pylint: disable=protected-access
    return looks


def _restore_looks(shape: BaseShape, looks: dict) -> None:
    """Give the new paragraphs and runs of a shape the properties it had at their level."""
    for paragraph in shape.text_frame.paragraphs:
        if paragraph.level in looks:
            _restore_paragraph_look(paragraph, looks[paragraph.level][0])
        if look := looks.get(paragraph.level) or looks.get(0):
            for run in paragraph.runs:
                if run.font.name != MONO_FONT:
                    merge_run_properties(run, look[1])


def _restore_paragraph_look(paragraph, properties) -> None:
    """
    Give a new paragraph the properties of the shape's paragraph at its level.

    Its bullets and numbering replace the renderer's, unless only the new text is a list.
    """
    element = paragraph._p  # noqa: SLF001 # pylint: disable=protected-access
    rendered, number = element.get_or_add_pPr(), _rendered_number(paragraph)
    if not _is_list(properties) and (_is_list(rendered) or number):
        return
    if number and properties.find(qn("a:buAutoNum")) is not None:
        element.remove(number._r)  # noqa: SLF001 # pylint: disable=protected-access
    element.remove(rendered)
    if properties is not None:
        element.insert(0, copy.deepcopy(properties))


def _is_list(properties) -> bool:
    return properties is not None and any(properties.find(tag) is not None for tag in LIST_MARKERS)


def _rendered_number(paragraph):
    """The run holding the number the renderer wrote at the start of an item, if any."""
    runs = paragraph.runs
    return runs[0] if runs and RENDERED_NUMBER.fullmatch(runs[0].text) else None


def _layout_sample(shape: BaseShape):
    """
    The placeholder of a shape's layout, when the layout styles it on its sample
    text rather than in its own style, as LibreOffice does.
    """
    layout = shape._base_placeholder if shape.is_placeholder else None  # noqa: SLF001 # pylint: disable=protected-access
    body = layout._element.txBody if layout is not None else None  # noqa: SLF001 # pylint: disable=protected-access
    if body is None:
        return None
    # Both the list style and its levels are optional: an empty or missing one styles nothing.
    own_style = body.find(qn("a:lstStyle"))
    if own_style is not None and len(own_style):
        return None
    return layout


def _is_title(shape: BaseShape) -> bool:
    return shape.is_placeholder and shape.placeholder_format.type in (
        PP_PLACEHOLDER.TITLE,
        PP_PLACEHOLDER.CENTER_TITLE,
    )


def _describe(shape: BaseShape) -> str:
    """A shape as the agent sees it: its id, kind and size, for its text to fit it."""
    # A shape may have no size of its own nor any to inherit from its layout.
    if shape.width is None or shape.height is None:
        return f"shape {shape.shape_id} ({_shape_kind(shape)})"
    size = f"{shape.width.cm:.0f}×{shape.height.cm:.0f} cm"
    return f"shape {shape.shape_id} ({_shape_kind(shape)}, {size})"


def _shape_kind(shape: BaseShape) -> str:
    """How a shape is described to the agent: its placeholder type, a table or a text box."""
    if shape.has_table:
        return "table"
    if shape.is_placeholder:
        kind = shape.placeholder_format.type
        return "body" if kind == PP_PLACEHOLDER.OBJECT else kind.name.lower()
    return "text box"


def _non_text_content(shape: BaseShape) -> str | None:
    """The kind of content of a shape that copies keep as it is, if any."""
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        return "picture"
    if shape.has_chart:
        return "chart"
    return None
