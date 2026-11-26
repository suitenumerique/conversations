"""Render Markdown into pptx shapes.

The model writes slide content as Markdown; this module turns it into formatted
runs, bulleted lists and tables inside a placeholder. Markdown is converted to
HTML first, then walked with BeautifulSoup, both of which the project already
depends on.

Inline styles are only ever set when the Markdown asks for them, never reset to
their falsy value, so the template's own styling keeps applying otherwise.
"""

import copy
import re
from dataclasses import dataclass

import markdown as markdown_lib
from bs4 import BeautifulSoup, NavigableString, Tag
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.shapes.base import BaseShape
from pptx.table import Table
from pptx.text.text import TextFrame, _Paragraph
from pptx.util import Emu, Pt

BULLET_CHAR = "•"
MONO_FONT = "Consolas"
MONO_FONT_SIZE = Pt(10)
# The run properties that make a run a link.
HYPERLINKS = (qn("a:hlinkClick"), qn("a:hlinkMouseOver"))

HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

UNORDERED_LIST_TAG = "ul"
ORDERED_LIST_TAG = "ol"
LIST_TAGS = (UNORDERED_LIST_TAG, ORDERED_LIST_TAG)

# Inline tags the renderer understands; anything else is walked through for its
# text without adding style.
LINE_BREAK_TAG = "br"
BOLD_TAGS = ("strong", "b")
ITALIC_TAGS = ("em", "i")
UNDERLINE_TAG = "u"
CODE_TAG = "code"
LINK_TAG = "a"

# Table tags, as produced by the Markdown ``tables`` extension.
TABLE_TAG = "table"
TABLE_ROW_TAG = "tr"
TABLE_HEADER_GROUP_TAG = "thead"
TABLE_HEADER_CELL_TAG = "th"
TABLE_DATA_CELL_TAG = "td"
# A list, not a tuple: BeautifulSoup's find_all only treats a list as a set of
# alternative tag names to match.
TABLE_CELL_TAGS = [TABLE_HEADER_CELL_TAG, TABLE_DATA_CELL_TAG]

# Slide content is model-generated, so only allow safe link schemes to reach the
# deck; anything else (e.g. ``javascript:``, ``data:``) is dropped.
SAFE_LINK_SCHEMES = ("http://", "https://", "mailto:")

# Left indent of a bullet level, and the hanging indent pulling the bullet
# character back into the margin, in EMU.
INDENT_PER_LEVEL = 342900
HANGING_INDENT = -342900

# A list item line: its indentation, and its number if it is a numbered item.
LIST_ITEM = re.compile(r"^( *)(?:(\d+)\.|[-*+]) ")


def render(target: BaseShape | TextFrame, markdown_text: str) -> BaseShape | TextFrame:
    """
    Render Markdown into a shape or a text frame, and return what holds the content.

    A Markdown table takes over the whole placeholder: when one is present, the
    rest of the content in the same field is dropped, because a pptx table is a
    separate graphic frame rather than something that can flow with text. That
    frame is what is returned then. A text frame, such as speaker notes, cannot
    hold a table: its rows are written as lines of text.
    """
    html = markdown_lib.markdown(
        _normalize_lists(markdown_text or ""), extensions=["tables", "sane_lists"]
    )
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find(TABLE_TAG)
    if table is not None and isinstance(target, BaseShape):
        return _render_table(target, table) or target

    text_frame = target.text_frame if hasattr(target, "text_frame") else target
    _render_text(text_frame, soup)
    return target


def _normalize_lists(markdown_text: str) -> str:
    """
    Accept the list syntax models write, which python-markdown is strict about.

    Python-markdown only nests items indented by 4 spaces, and only starts a
    list, or switches between bulleted and numbered ones, after a blank line.
    Models often nest by 2 spaces, and write lists right under a line of text
    or right after a list of the other kind: all are fixed up here.
    """
    lines = markdown_text.split("\n")
    items = [LIST_ITEM.match(line) for line in lines]
    if any(len(item[1]) % 4 for item in items if item):
        lines = [item[1] + line if item else line for item, line in zip(items, lines, strict=True)]

    normalized = []
    for index, (line, item) in enumerate(zip(lines, items, strict=True)):
        previous = items[index - 1] if index else None
        continues_list = previous and item and bool(previous[2]) == bool(item[2])
        if item and normalized and normalized[-1].strip() and not continues_list:
            normalized.append("")
        normalized.append(line)
    return "\n".join(normalized)


@dataclass
class _RenderContext:
    """Tracks the text frame being filled and whether its first paragraph is used."""

    text_frame: TextFrame
    first_paragraph_used: bool = False


@dataclass
class _InlineState:
    """Inline styles accumulated while walking down nested inline tags."""

    bold: bool = False
    italic: bool = False
    underline: bool = False
    mono: bool = False
    link: str | None = None


def _render_text(text_frame: TextFrame, soup: BeautifulSoup) -> None:
    """Fill a text frame with the block-level content of the parsed Markdown."""
    text_frame.clear()
    text_frame.word_wrap = True
    context = _RenderContext(text_frame=text_frame)

    for node in soup.contents:
        if isinstance(node, NavigableString) and not str(node).strip():
            continue

        name = getattr(node, "name", None)
        if name in HEADING_TAGS:
            paragraph = _new_paragraph(context)
            _render_inline_children(paragraph, node)
            for run in paragraph.runs:
                run.font.bold = True
        elif name in LIST_TAGS:
            _render_list(context, node, level=0, ordered=name == ORDERED_LIST_TAG)
        elif name == TABLE_TAG:
            for row in node.find_all(TABLE_ROW_TAG):
                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(TABLE_CELL_TAGS)]
                _new_paragraph(context).add_run().text = " | ".join(cells)
        else:
            paragraph = _new_paragraph(context)
            _render_inline_children(paragraph, node)


def _render_table(shape: BaseShape, table_node: Tag) -> BaseShape | None:
    """Replace a placeholder's content with a pptx table built from an HTML table."""
    rows = table_node.find_all(TABLE_ROW_TAG)
    if not rows:
        return None

    row_count = len(rows)
    column_count = max(len(row.find_all(TABLE_CELL_TAGS)) for row in rows)

    if hasattr(shape, "insert_table"):
        graphic_frame = shape.insert_table(rows=row_count, cols=column_count)
    else:
        # On the slide itself: the shapes of a group cannot add a table. A shape
        # with no size of its own gives its place to a table across the slide.
        presentation = shape.part.package.presentation_part.presentation
        left, top = shape.left or 0, shape.top or 0
        graphic_frame = shape.part.slide.shapes.add_table(
            row_count,
            column_count,
            left,
            top,
            shape.width or presentation.slide_width - 2 * left,
            shape.height or presentation.slide_height - 2 * top,
        )

    _fill_table(graphic_frame.table, rows, bold_header=True)
    return graphic_frame


def render_into_table(table: Table, markdown_text: str) -> None:
    """
    Fill the cells of an existing table from a Markdown table.

    The table is fitted to the Markdown, so that none of its own content is left
    behind and none of the Markdown's is lost: it gets copies of its last column
    and row for the columns and rows the Markdown adds, loses the rows it does
    not have, and its cells past the Markdown's columns are emptied.
    """
    html = markdown_lib.markdown(markdown_text or "", extensions=["tables"])
    rows = BeautifulSoup(html, "html.parser").find_all(TABLE_ROW_TAG)
    if not rows:
        return  # Not a Markdown table: the user's table is left as it is.
    tbl = table._tbl  # noqa: SLF001 # pylint: disable=protected-access
    _add_columns(tbl, max(len(row.find_all(TABLE_CELL_TAGS)) for row in rows))
    _fit_row_count(tbl, len(rows))
    _fill_table(table, rows)
    for row, row_node in zip(table.rows, rows, strict=True):
        for cell in list(row.cells)[len(row_node.find_all(TABLE_CELL_TAGS)) :]:
            if not cell.is_spanned:
                cell.text_frame.text = ""


def _add_columns(tbl, count: int) -> None:
    """
    Give a table copies of its last column up to ``count`` columns, keeping its
    width: the columns share it as they shared it before.
    """
    grid = tbl.tblGrid
    width = sum(column.w for column in grid.gridCol_lst)
    for _ in range(count - len(grid.gridCol_lst)):
        grid.gridCol_lst[-1].addnext(copy.deepcopy(grid.gridCol_lst[-1]))
        for row in tbl.tr_lst:
            cell = copy.deepcopy(row.tc_lst[-1])
            cell.attrib.pop("hMerge", None)  # A new column continues no merge.
            row.tc_lst[-1].addnext(cell)
        _drop_extensions(grid.gridCol_lst[-1])
    new_width = sum(column.w for column in grid.gridCol_lst)
    if new_width != width:
        for column in grid.gridCol_lst:
            column.w = Emu(column.w * width // new_width)


def _fit_row_count(tbl, count: int) -> None:
    """
    Give a table copies of its last row, or remove its last rows, up to ``count``
    rows, keeping its vertical merges within the table.
    """
    for _ in range(count - len(tbl.tr_lst)):
        row = copy.deepcopy(tbl.tr_lst[-1])
        for cell in row.tc_lst:
            cell.attrib.pop("vMerge", None)  # A new row continues no merge.
        _drop_extensions(row)
        tbl.tr_lst[-1].addnext(row)
    for extra_row in tbl.tr_lst[count:]:
        tbl.remove(extra_row)
    for index, row in enumerate(tbl.tr_lst):
        for cell in row.tc_lst:
            cell.rowSpan = min(cell.rowSpan, count - index)


def _drop_extensions(element) -> None:
    """
    Drop the extensions of a copied row or column: they hold its id, which
    PowerPoint wants unique in the table.
    """
    for extensions in element.findall(qn("a:extLst")):
        element.remove(extensions)


def _fill_table(table: Table, rows: list[Tag], bold_header: bool = False) -> None:
    """
    Fill a table's cells with the inline content of HTML table rows, the header
    in bold with ``bold_header``: a user's table keeps the header it has.

    A changed cell keeps the look of its first run. Text for a cell a merge
    hides splits that merge, or it would not show.
    """
    for row_index, row_node in enumerate(rows[: len(table.rows)]):
        is_header_row = bold_header and row_node.parent.name == TABLE_HEADER_GROUP_TAG
        cell_nodes = row_node.find_all(TABLE_CELL_TAGS)[: len(table.columns)]
        for column_index, cell_node in enumerate(cell_nodes):
            cell = table.cell(row_index, column_index)
            if cell_node.get_text(" ").split() == cell.text.split():
                continue  # Keeps the formatting of the cells that do not change.
            if cell.is_spanned:
                _split_merge_over(table, row_index, column_index)
            look = _first_run_look(cell)
            cell.text_frame.clear()
            cell.text_frame.word_wrap = True

            paragraph = cell.text_frame.paragraphs[0]
            paragraph.clear()
            _render_inline_children(paragraph, cell_node)

            for run in paragraph.runs:
                if look is not None and run.font.name != MONO_FONT:
                    merge_run_properties(run, look)
                if is_header_row or (bold_header and cell_node.name == TABLE_HEADER_CELL_TAG):
                    run.font.bold = True


def _split_merge_over(table: Table, row_index: int, column_index: int) -> None:
    """Split the merge that hides a table's cell."""
    for origin_row in range(row_index + 1):
        for origin_column in range(column_index + 1):
            origin = table.cell(origin_row, origin_column)
            if (
                origin.is_merge_origin
                and row_index < origin_row + origin.span_height
                and column_index < origin_column + origin.span_width
            ):
                origin.split()
                return


def _first_run_look(cell):
    """The properties of a cell's first run, but its link, for new text to take."""
    run = next((run for paragraph in cell.text_frame.paragraphs for run in paragraph.runs), None)
    if run is None:
        return None
    look = copy.deepcopy(run._r.get_or_add_rPr())  # noqa: SLF001 # pylint: disable=protected-access
    for link in [*look.iterchildren(*HYPERLINKS)]:
        look.remove(link)
    return look


def _new_paragraph(context: _RenderContext) -> _Paragraph:
    """Reuse the text frame's initial empty paragraph, then append new ones."""
    if not context.first_paragraph_used:
        paragraph = context.text_frame.paragraphs[0]
        paragraph.clear()
        context.first_paragraph_used = True
        return paragraph
    return context.text_frame.add_paragraph()


def _render_list(context: _RenderContext, list_node: Tag, level: int, ordered: bool) -> None:
    """Render a list and its nested lists, one paragraph per item."""
    items = list_node.find_all("li", recursive=False)
    for index, item in enumerate(items, start=int(list_node.get("start", 1))):
        _render_list_item(context, item, level, ordered, index)


def _render_list_item(
    context: _RenderContext, item: Tag, level: int, ordered: bool, index: int
) -> None:
    """Render one list item: its text into a marked paragraph, nested lists apart."""
    paragraph = None
    for child in item.contents:
        name = getattr(child, "name", None)

        if name in LIST_TAGS:
            _render_list(context, child, level + 1, ordered=name == ORDERED_LIST_TAG)
            continue

        if isinstance(child, NavigableString) and not str(child).strip():
            continue

        if paragraph is None:
            paragraph = _new_paragraph(context)
            _mark_list_paragraph(paragraph, level, ordered, index)

        _add_inline(paragraph, child)


def _mark_list_paragraph(paragraph: _Paragraph, level: int, ordered: bool, index: int) -> None:
    """Give a list item's paragraph its number or bullet."""
    if ordered:
        _apply_number(paragraph, level, index)
    else:
        _apply_bullet(paragraph, level)


def _render_inline_children(paragraph: _Paragraph, node: Tag) -> None:
    """Render every inline child of a block node into one paragraph."""
    for child in node.contents:
        _add_inline(paragraph, child)


def _add_inline(
    paragraph: _Paragraph,
    node: Tag | NavigableString,
    state: _InlineState | None = None,
) -> None:
    """Walk an inline subtree, emitting one run per text node with its styles."""
    state = state or _InlineState()

    if isinstance(node, NavigableString):
        if text := str(node):
            run = paragraph.add_run()
            run.text = text
            _apply_run_style(run, state)
        return

    tag = (node.name or "").lower()
    if tag == LINE_BREAK_TAG:
        paragraph.add_line_break()
        return

    nested_state = _InlineState(
        bold=state.bold or tag in BOLD_TAGS,
        italic=state.italic or tag in ITALIC_TAGS,
        underline=state.underline or tag == UNDERLINE_TAG,
        mono=state.mono or tag == CODE_TAG,
        link=node.get("href") if tag == LINK_TAG else state.link,
    )
    for child in node.contents:
        _add_inline(paragraph, child, nested_state)


def _apply_run_style(run, state: _InlineState) -> None:
    """Apply the accumulated inline styles, leaving unset ones to the template."""
    if state.bold:
        run.font.bold = True
    if state.italic:
        run.font.italic = True
    if state.underline:
        run.font.underline = True
    if state.mono:
        run.font.name = MONO_FONT
        run.font.size = MONO_FONT_SIZE
    if state.link and state.link.lower().startswith(SAFE_LINK_SCHEMES):
        run.hyperlink.address = state.link


def _paragraph_properties(paragraph: _Paragraph):
    """Return the paragraph's ``<a:pPr>`` element, creating it if needed."""
    # pylint: disable=protected-access
    return paragraph._p.get_or_add_pPr()  # noqa: SLF001


def _clear_bullet_properties(properties) -> None:
    """Drop any bullet definition inherited from the layout."""
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        element = properties.find(qn(tag))
        if element is not None:
            properties.remove(element)


def _apply_indent(properties, paragraph: _Paragraph, level: int) -> None:
    """Indent a paragraph to its nesting level, with a hanging first line."""
    properties.set("marL", str(INDENT_PER_LEVEL * (level + 1)))
    properties.set("indent", str(HANGING_INDENT))
    paragraph.level = level


def _apply_bullet(paragraph: _Paragraph, level: int) -> None:
    """Give an unordered list item its bullet character."""
    properties = _paragraph_properties(paragraph)
    _clear_bullet_properties(properties)
    _apply_indent(properties, paragraph, level)

    bullet = OxmlElement("a:buChar")
    bullet.set("char", BULLET_CHAR)
    properties.append(bullet)


def _apply_number(paragraph: _Paragraph, level: int, index: int) -> None:
    """
    Prefix an ordered list item with its number as plain text.

    Auto-numbering is not used on purpose: it restarts per shape and cannot be
    controlled per nesting level here, which produced wrong numbers on nested
    ordered lists.
    """
    properties = _paragraph_properties(paragraph)
    _clear_bullet_properties(properties)
    properties.append(OxmlElement("a:buNone"))
    _apply_indent(properties, paragraph, level)

    run = paragraph.add_run()
    run.text = f"{index}. "


def merge_run_properties(run, look) -> None:
    """Set a run's properties to a copy of ``look``, under the ones the run sets itself."""
    own = run._r.get_or_add_rPr()  # noqa: SLF001 # pylint: disable=protected-access
    merged = copy.deepcopy(look)
    for name, value in own.attrib.items():
        merged.set(name, value)
    # Only a hyperlink: the renderer sets fonts on code runs alone. A copy of the
    # list, as appending a child elsewhere moves it out of ``own``.
    for child in list(own):
        merged.append(child)
    own.getparent().replace(own, merged)
