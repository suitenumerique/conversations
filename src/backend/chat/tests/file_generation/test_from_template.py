"""
Tests for building a deck out of the user's own slides.

Real components: python-pptx. The user's deck is made with python-pptx's own
default template, built in memory and read back as a user would open it.
"""

import zipfile
from io import BytesIO
from pathlib import Path

import pptx
import pytest
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.opc.constants import CONTENT_TYPE as CT
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

from chat.file_generation import (
    PresentationStyle,
    TemplatedPresentation,
    TemplatedSlide,
    TemplateTooLargeError,
    build_from_template,
    from_template,
    outline_template,
)

PICTURE = Path(__file__).parents[3] / "core/static/images/logo.png"
A16 = "{http://schemas.microsoft.com/office/drawing/2014/main}"
RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A16_ROW_ID, A16_COLUMN_ID = f"{A16}rowId", f"{A16}colId"


def user_deck() -> bytes:
    """A cover, then a content slide holding a picture and hand-sized text."""
    deck = pptx.Presentation()
    cover = deck.slides.add_slide(deck.slide_layouts[0])
    cover.shapes.title.text = "Titre de la présentation"
    cover.placeholders[1].text = "Direction - date"

    content = deck.slides.add_slide(deck.slide_layouts[1])
    content.shapes.title.text = "Titre de contenu"
    content.placeholders[1].text = "Texte d'exemple"
    content.placeholders[1].text_frame.paragraphs[0].runs[0].font.size = Pt(20)
    content.shapes.add_picture(str(PICTURE), Inches(8), Inches(6), Inches(1))

    blob = BytesIO()
    deck.save(blob)
    return blob.getvalue()


def build(*slides, style=None):
    """Build a deck out of the user's slides and reopen it."""
    presentation = TemplatedPresentation(title="Deck", slides=list(slides))
    blob = build_from_template(user_deck(), presentation, style or PresentationStyle())
    return pptx.Presentation(BytesIO(blob))


def texts(slide):
    """The texts of the text shapes of a slide."""
    return [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]


def file_parts(output: bytes) -> dict[str, bytes]:
    """The parts of a pptx file, by name."""
    with zipfile.ZipFile(BytesIO(output)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def dangling_links(parts: dict[str, bytes]) -> list[str]:
    """The relationship ids the XML parts of a pptx file use but do not define."""
    found = []
    for name, content in parts.items():
        if not name.endswith(".xml") or name == "[Content_Types].xml":
            continue
        folder, _, file_name = name.rpartition("/")
        rels = parts.get(f"{folder}/_rels/{file_name}.rels", b"")
        defined = {node.get("Id") for node in parse_xml(rels).iter()} if rels else set()
        found += [
            f"{name}: {value}"
            for node in parse_xml(content).iter()
            for attribute, value in node.attrib.items()
            if attribute.startswith(RELATIONSHIP_NAMESPACE) and value and value not in defined
        ]
    return found


def test_the_outline_describes_each_slide():
    """The agent sees each slide's text shapes, their ids and texts, and other content."""
    outline = outline_template(user_deck())

    assert outline.shape_ids == (frozenset({2, 3}), frozenset({2, 3}))
    assert "Slide 1, layout 'Title Slide':" in outline.description
    assert '- shape 2 (center_title, 22×4 cm): "Titre de la présentation"' in outline.description
    assert '- shape 3 (body, 23×13 cm): "Texte d\'exemple"' in outline.description
    assert "- also holds: picture" in outline.description
    assert (
        "Layout 'Title and Content':\n- shape 2 (title, 23×3 cm)\n- shape 3 (body, 23×13 cm)"
        in (outline.description)
    )
    assert outline.layout_shape_ids["Title and Content"] == frozenset({2, 3})
    # A picture slot takes no text: the agent is not offered it.
    assert outline.layout_shape_ids["Picture with Caption"] == frozenset({2, 4})
    assert "(picture," not in outline.description


def test_a_shape_without_a_size_is_described_and_rewritten():
    """A text box with no size of its own, valid in a pptx, is described without one."""
    deck = pptx.Presentation()
    box = deck.slides.add_slide(deck.slide_layouts[6]).shapes.add_textbox(0, 0, 1, 1)
    box.text = "Sans taille"
    box._element.spPr.remove(box._element.spPr.find(qn("a:xfrm")))  # pylint: disable=protected-access
    blob = BytesIO()
    deck.save(blob)

    assert '- shape 2 (text box): "Sans taille"' in outline_template(blob.getvalue()).description
    # Its text is not fitted to a size it does not have.
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(template_slide=1, texts={2: "Nouveau texte"})]
    )
    built = build_from_template(blob.getvalue(), presentation, PresentationStyle())
    assert texts(pptx.Presentation(BytesIO(built)).slides[0]) == ["Nouveau texte"]
    # A table given its place spans the slide.
    presentation.slides[0].texts[2] = "| Poste |\n|---|\n| Total |"
    built = build_from_template(blob.getvalue(), presentation, PresentationStyle())
    (table,) = pptx.Presentation(BytesIO(built)).slides[0].shapes
    assert [cell.text for cell in table.table.iter_cells()] == ["Poste", "Total"]


def test_a_slide_can_be_made_from_a_layout():
    """A new slide made from one of the user's layouts gets its placeholders filled."""
    deck = build(
        TemplatedSlide(template_slide=1),
        TemplatedSlide(layout="Title and Content", texts={2: "Résumé", 3: "- un\n- deux"}),
    )

    assert len(deck.slides) == 2
    assert deck.slides[1].slide_layout.name == "Title and Content"
    assert texts(deck.slides[1]) == ["Résumé", "un\ndeux"]


def test_slides_are_copied_with_new_texts_and_the_originals_dropped():
    """Each new slide copies a user's slide, keeps its picture, and gets its new texts."""
    deck = build(
        TemplatedSlide(template_slide=1, texts={2: "Plan vélo", 3: "Comité"}),
        TemplatedSlide(template_slide=2, texts={2: "Constats", 3: "- un\n- deux"}),
        TemplatedSlide(template_slide=2, texts={2: "Suite", 3: "Trois"}),
    )

    assert [texts(slide) for slide in deck.slides] == [
        ["Plan vélo", "Comité"],
        ["Constats", "un\ndeux"],
        ["Suite", "Trois"],
    ]
    for slide in list(deck.slides)[1:]:
        picture = next(s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE)
        assert picture.image.blob == PICTURE.read_bytes()


def test_an_empty_text_removes_a_shape():
    """A shape the new slide does not use, a sample text or a table, is removed."""
    deck = build(TemplatedSlide(template_slide=2, texts={2: "Titre de contenu", 3: ""}))

    assert texts(deck.slides[0]) == ["Titre de contenu"]
    # A shape that holds no text, such as a filled tile, is removed as well.
    user = pptx.Presentation()
    tile = user.slides.add_slide(user.slide_layouts[6]).shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1)
    )
    blob = BytesIO()
    user.save(blob)
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(template_slide=1, texts={tile.shape_id: ""})]
    )
    built = build_from_template(blob.getvalue(), presentation, PresentationStyle())
    assert len(pptx.Presentation(BytesIO(built)).slides[0].shapes) == 0


def test_a_shape_given_no_text_or_its_own_is_kept_as_it_is():
    """A shape left out, or given back its text, keeps its hand-set formatting untouched."""
    deck = build(TemplatedSlide(template_slide=2, texts={2: "Constats", 3: "Texte d'exemple\n"}))

    body = deck.slides[0].shapes[1].text_frame
    assert body.text == "Texte d'exemple"
    assert body.paragraphs[0].runs[0].font.size == Pt(20)
    # The same words split into paragraphs are a new text.
    split = build(TemplatedSlide(template_slide=2, texts={3: "Texte\n\nd'exemple"}))
    assert split.slides[0].shapes[1].text_frame.text == "Texte\nd'exemple"


def test_a_shape_keeping_its_text_takes_the_style_fields_asked_for():
    """A restyled deck changes everywhere, but for the fields the user did not set."""
    style = PresentationStyle(title_size=40, text_color="#E1000F")
    deck = build(TemplatedSlide(template_slide=2, texts={3: "Texte d'exemple"}), style=style)

    title, body = (
        shape.text_frame.paragraphs[0].runs[0].font for shape in list(deck.slides[0].shapes)[:2]
    )
    assert title.size == Pt(40)
    assert body.color.rgb == RGBColor.from_string("E1000F")
    assert body.size == Pt(20)
    # Given a colour only, a text box keeps how it fits, and a table its sizes.
    assert deck.slides[0].shapes[1].text_frame.auto_size is None
    blob = deck_with_table_group_and_chart()
    table_slide = TemplatedPresentation(title="Deck", slides=[TemplatedSlide(template_slide=1)])
    restyled = pptx.Presentation(BytesIO(build_from_template(blob, table_slide, style)))
    table = next(shape for shape in restyled.slides[0].shapes if shape.has_table).table
    assert {
        run.font.size for cell in table.iter_cells() for run in cell.text_frame.paragraphs[0].runs
    } == {None}


def test_the_look_of_hand_formatted_text_is_kept_under_the_style():
    """New text keeps the size set by hand on the text it replaces, and takes the style."""
    deck = build(
        TemplatedSlide(template_slide=2, texts={2: "Constats", 3: "Nouveau texte"}),
        style=PresentationStyle(text_color="#000091"),
    )

    run = deck.slides[0].shapes[1].text_frame.paragraphs[0].runs[0]
    assert run.font.size == Pt(20)
    assert str(run.font.color.rgb) == "000091"


def test_new_text_does_not_take_the_links_of_the_text_it_replaces():
    """A shape starting with a link gives its look to new text, not its link."""
    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    body = slide.placeholders[1]
    link = body.text_frame.paragraphs[0].add_run()
    link.text = "Voir le site"
    link.hyperlink.address = "https://ancien.example"
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(
        title="Deck",
        slides=[
            TemplatedSlide(
                template_slide=1,
                texts={body.shape_id: "- [Nouveau site](https://nouveau.example) et suite"},
            )
        ],
    )

    built = pptx.Presentation(
        BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
    )

    runs = built.slides[0].placeholders[1].text_frame.paragraphs[0].runs
    assert [(run.text, run.hyperlink.address) for run in runs] == [
        ("Nouveau site", "https://nouveau.example"),
        (" et suite", None),
    ]


def test_a_rewritten_list_keeps_the_numbering_of_the_shape():
    """An agenda given a new entry keeps its own automatic numbering, not a typed one."""
    deck = pptx.Presentation()
    agenda = deck.slides.add_slide(deck.slide_layouts[1])
    agenda.placeholders[1].text = "Budget\nProjects"
    for paragraph in agenda.placeholders[1].text_frame.paragraphs:
        numbering = OxmlElement("a:buAutoNum")
        numbering.set("type", "arabicPeriod")
        paragraph._p.get_or_add_pPr().append(numbering)  # pylint: disable=protected-access
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(
        title="Deck",
        slides=[TemplatedSlide(template_slide=1, texts={3: "1. Budget\n2. Cyber\n3. Projects"})],
    )

    body = (
        pptx.Presentation(
            BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
        )
        .slides[0]
        .placeholders[1]
        .text_frame
    )
    assert [paragraph.text for paragraph in body.paragraphs] == ["Budget", "Cyber", "Projects"]
    assert all(
        paragraph._p.pPr.find(qn("a:buAutoNum")) is not None  # pylint: disable=protected-access
        for paragraph in body.paragraphs
    )


def test_a_background_colour_asked_for_is_given_to_every_slide():
    """It replaces the background of the user's slides; without one, theirs is kept."""
    style = PresentationStyle(background_color="#000000")
    deck = build(TemplatedSlide(template_slide=1), TemplatedSlide(template_slide=2), style=style)

    assert [slide.background.fill.fore_color.rgb for slide in deck.slides] == [
        RGBColor.from_string("000000")
    ] * 2
    assert build(TemplatedSlide(template_slide=1)).slides[0].follow_master_background


def test_presenter_notes_are_attached():
    """The agent's speaker notes go to the notes of the slide."""
    deck = build(TemplatedSlide(template_slide=1, slide_notes="À dire à l'oral"))

    assert deck.slides[0].notes_slide.notes_text_frame.text == "À dire à l'oral"


def test_notes_are_skipped_when_the_user_notes_have_no_text_area():
    """A notes master without a body placeholder gives no place for notes: the deck is built."""
    deck = pptx.Presentation()
    deck.slides.add_slide(deck.slide_layouts[5])
    for placeholder in list(deck.notes_master.placeholders):
        if placeholder.placeholder_format.type == PP_PLACEHOLDER.BODY:
            placeholder._element.getparent().remove(placeholder._element)  # pylint: disable=protected-access
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(template_slide=1, slide_notes="À dire")]
    )

    built = build_from_template(blob.getvalue(), presentation, PresentationStyle())

    assert len(pptx.Presentation(BytesIO(built)).slides) == 1


def test_a_copy_keeps_the_speaker_notes_of_its_slide_unless_given_new_ones():
    """The notes are shown to the agent, kept on every copy, and replaced by new ones."""
    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.notes_slide.notes_text_frame.text = "Rappeler le contexte"
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(
        title="Deck",
        slides=[
            TemplatedSlide(template_slide=1),
            TemplatedSlide(template_slide=1, slide_notes="Nouvelle note"),
        ],
    )

    built = pptx.Presentation(
        BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
    )

    assert (
        '- speaker notes: "Rappeler le contexte"' in outline_template(blob.getvalue()).description
    )
    notes = [copy.notes_slide.notes_text_frame.text for copy in built.slides]
    assert notes == ["Rappeler le contexte", "Nouvelle note"]


def test_the_outline_rejects_slides_and_shapes_the_user_deck_does_not_have():
    """The agent is told what it copied that does not exist, to correct it."""
    outline = outline_template(user_deck())

    def check(*slides):
        return outline.check(TemplatedPresentation(title="Deck", slides=list(slides)))

    assert check(TemplatedSlide(template_slide=2, texts={2: "ok"})) is None
    assert "copies slide 5" in check(TemplatedSlide(template_slide=5))
    assert "must either copy" in check(TemplatedSlide())
    assert "must either copy" in check(TemplatedSlide(template_slide=1, layout="Title Only"))
    assert "shapes [9]" in check(TemplatedSlide(template_slide=1, texts={9: "?"}))
    assert "layout 'Inconnu'" in check(TemplatedSlide(layout="Inconnu"))
    assert "its shapes are [2]" in check(TemplatedSlide(layout="Title Only", texts={9: "?"}))
    copied_twice = check(
        TemplatedSlide(template_slide=2, texts={2: "Un", 3: "un"}),
        TemplatedSlide(template_slide=2, texts={2: "Deux"}),
    )
    assert "copied several times, but gives no text to shapes [3]" in copied_twice


def deck_with_table_group_and_chart() -> bytes:
    """One slide holding a table, a group of two labelled tiles, and a chart."""
    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    table = slide.shapes.add_table(2, 2, Inches(0.5), Inches(0.5), Inches(4), Inches(1)).table
    for row, values in enumerate([("Poste", "Montant | TTC"), ("Fonctionnement", "820 k€\nvoté")]):
        table.cell(row, 0).text, table.cell(row, 1).text = values
    group = slide.shapes.add_group_shape()
    for index, label in enumerate(["Projet A", "Projet B"]):
        tile = group.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.5 + 2 * index), Inches(2), Inches(1.5), Inches(1)
        )
        tile.text_frame.text = label
    chart_data = CategoryChartData()
    chart_data.categories = ["2025"]
    chart_data.add_series("Visites", (4210,))
    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(5), Inches(0.5), Inches(4), Inches(3), chart_data
    )
    blob = BytesIO()
    deck.save(blob)
    return blob.getvalue()


def test_tables_and_grouped_texts_are_described_and_filled():
    """A table is shown and filled as a Markdown table; texts inside groups change too."""
    blob = deck_with_table_group_and_chart()
    outline = outline_template(blob)
    table_id, *tile_ids = sorted(outline.shape_ids[0])

    assert (
        '(table, 10×3 cm): "| Poste | Montant \\\\| TTC |\\n|---|---|\\n'
        '| Fonctionnement | 820 k€<br>voté |"' in (outline.description)
    )
    assert '"Projet A"' in outline.description

    presentation = TemplatedPresentation(
        title="Deck",
        slides=[
            TemplatedSlide(
                template_slide=1,
                texts={
                    table_id: (
                        "| Poste | Montant \\| TTC |\n|---|---|\n"
                        "| Fonctionnement | 850 k€<br>voté |"
                    ),
                    tile_ids[0]: "Portail v2",
                    tile_ids[1]: "Archives orales",
                },
            )
        ],
    )
    slide = pptx.Presentation(
        BytesIO(build_from_template(blob, presentation, PresentationStyle()))
    ).slides[0]

    table = next(shape for shape in slide.shapes if shape.has_table).table
    assert table.cell(0, 1).text == "Montant | TTC"
    assert table.cell(1, 1).text == "850 k€\vvoté"
    group = next(shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.GROUP)
    assert [tile.text_frame.text for tile in group.shapes] == ["Portail v2", "Archives orales"]


def test_a_markdown_table_takes_the_place_of_a_text_shape():
    """The text it replaces is not left under it, in a group too."""
    table = "| Poste | Montant |\n|---|---|\n| Total | 2 M€ |"
    body_slide = build(TemplatedSlide(template_slide=2, texts={2: "Budget", 3: table})).slides[0]

    assert texts(body_slide) == ["Budget"]
    body_top = body_slide.slide_layout.placeholders[1].top
    assert next(shape for shape in body_slide.shapes if shape.has_table).top == body_top

    blob = deck_with_table_group_and_chart()
    tile_id = sorted(outline_template(blob).shape_ids[0])[1]
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(template_slide=1, texts={tile_id: table})]
    )
    slide = pptx.Presentation(
        BytesIO(build_from_template(blob, presentation, PresentationStyle()))
    ).slides[0]

    group = next(shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.GROUP)
    assert [shape.has_table for shape in group.shapes] == [True, False]
    assert group.shapes[0].table.cell(1, 1).text == "2 M€"
    assert group.shapes[1].text_frame.text == "Projet B"


def test_a_table_put_in_a_table_slot_is_offered_and_filled():
    """A table inserted into a table placeholder stays a placeholder, and is still a table."""
    deck = pptx.Presentation()
    layout = deck.slide_layouts[1]
    layout.placeholders[1].element.ph.set("type", "tbl")
    slot = deck.slides.add_slide(layout).placeholders[1].insert_table(rows=2, cols=1)
    slot.table.cell(0, 0).text = "Poste"
    blob = BytesIO()
    deck.save(blob)
    outline = outline_template(blob.getvalue())

    assert slot.shape_id in outline.shape_ids[0]
    presentation = TemplatedPresentation(
        title="Deck",
        slides=[
            TemplatedSlide(template_slide=1, texts={slot.shape_id: "| Montant |\n|---|\n| 2 M€ |"})
        ],
    )
    built = pptx.Presentation(
        BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
    )
    table = next(shape for shape in built.slides[0].shapes if shape.has_table).table
    assert [cell.text for cell in table.iter_cells()] == ["Montant", "2 M€"]


def fill_table(markdown):
    """Give a new Markdown text to the table of the user's slide, and return the table."""
    blob = deck_with_table_group_and_chart()
    table_id = min(outline_template(blob).shape_ids[0])
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(template_slide=1, texts={table_id: markdown})]
    )
    slide = pptx.Presentation(
        BytesIO(build_from_template(blob, presentation, PresentationStyle()))
    ).slides[0]
    table = next(shape for shape in slide.shapes if shape.has_table).table
    return [[cell.text for cell in row.cells] for row in table.rows]


def test_a_table_is_fitted_to_the_rows_and_columns_of_its_new_text():
    """No sample content of the user's table is left behind, nor new content lost."""
    assert fill_table(
        "| Poste | Montant |\n|---|---|\n| Investissement | 1 M€ |\n| Total | 2 M€ |"
    ) == [
        ["Poste", "Montant"],
        ["Investissement", "1 M€"],
        ["Total", "2 M€"],
    ]
    assert fill_table("| Poste |\n|---|\n| Total |") == [["Poste", ""], ["Total", ""]]
    assert fill_table("| Poste | 2025 | 2026 |\n|---|---|---|\n| Total | 1 M€ | 2 M€ |") == [
        ["Poste", "2025", "2026"],
        ["Total", "1 M€", "2 M€"],
    ]
    assert fill_table("Pas un tableau") == [
        ["Poste", "Montant | TTC"],
        ["Fonctionnement", "820 k€\nvoté"],
    ]


def test_a_changed_cell_keeps_its_look_and_shows_through_merges():
    """
    A cell given new text keeps its hand-set font and colour. Text for a cell a
    merge hides splits the merge, and a merge outlives no removed row. A column
    narrower than its cells' margins still takes a new size.
    """
    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    table = slide.shapes.add_table(3, 3, Inches(0.5), Inches(0.5), Inches(6), Inches(2)).table
    for column, value in enumerate(["Poste", "2025", "2026"]):
        table.cell(0, column).text = value
    table.cell(1, 0).text, table.cell(1, 1).text, table.cell(1, 2).text = "Fonct.", "820", "900"
    look = table.cell(1, 1).text_frame.paragraphs[0].runs[0].font
    look.name, look.color.rgb = "Marianne", RGBColor(0xFF, 0xFF, 0xFF)
    table.cell(1, 0).merge(table.cell(2, 0))
    table.cell(2, 1).text = "Total"
    table.cell(2, 1).merge(table.cell(2, 2))
    table.columns[2].width = Inches(0.2)
    # PowerPoint gives each row and column an id, unique in the table.
    for index, element in enumerate([*table._tbl.tr_lst, *table._tbl.tblGrid.gridCol_lst]):  # pylint: disable=protected-access
        tag = "rowId" if element.tag == qn("a:tr") else "colId"
        element.append(
            parse_xml(
                '<a:extLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                f'<a:ext uri="{{0D108BD9-81ED-4DB2-BD59-A6C34878D82A}}"><a16:{tag} '
                f'xmlns:a16="http://schemas.microsoft.com/office/drawing/2014/main" val="{index}"/>'
                "</a:ext></a:extLst>"
            )
        )
    blob = BytesIO()
    deck.save(blob)
    table_id = min(outline_template(blob.getvalue()).shape_ids[0])

    def fill(markdown, style=None):
        presentation = TemplatedPresentation(
            title="Deck", slides=[TemplatedSlide(template_slide=1, texts={table_id: markdown})]
        )
        built = build_from_template(blob.getvalue(), presentation, style or PresentationStyle())
        shape = pptx.Presentation(BytesIO(built)).slides[0].shapes[0]
        return shape.table

    header = "| Poste | 2025 | 2026 |\n|---|---|---|\n"
    filled = fill(header + "| Fonct. | 850 | 900 |\n| Invest. | 1 | 2 |")
    assert [[cell.text for cell in row.cells] for row in filled.rows] == [
        ["Poste", "2025", "2026"],
        ["Fonct.", "850", "900"],
        ["Invest.", "1", "2"],
    ]
    assert not any(cell.is_merge_origin or cell.is_spanned for cell in filled.iter_cells())
    changed = filled.cell(1, 1).text_frame.paragraphs[0].runs[0].font
    assert (changed.name, changed.color.rgb) == ("Marianne", RGBColor(0xFF, 0xFF, 0xFF))
    # A changed header cell is not made bold: the user's header is not.
    retitled = fill(header.replace("2026", "2027") + "| Fonct. | 820 | 900 |")
    assert not retitled.cell(0, 2).text_frame.paragraphs[0].runs[0].font.bold
    grown = fill("| A | B | C | D |\n|---|---|---|---|\n" + "| 1 | 2 | 3 | 4 |\n" * 4)
    ids = [node.get("val") for node in grown._tbl.iter(A16_ROW_ID, A16_COLUMN_ID)]  # pylint: disable=protected-access
    assert len(ids) == len(set(ids)) == 6
    shortened = fill(header + "| Fonct. | 820 | 900 |")
    assert len(shortened.rows) == 2
    assert shortened.cell(1, 0).span_height == 1
    resized = fill(header + "| Fonct. | 820 | 900 |", PresentationStyle(text_size=12))
    assert resized.cell(1, 2).text_frame.paragraphs[0].runs[0].font.size is not None


def test_the_outline_tells_which_slides_hold_a_chart():
    """A copied chart keeps its data: the agent is told which slides hold one."""
    outline = outline_template(deck_with_table_group_and_chart())

    assert "- also holds: chart" in outline.description


def test_a_slide_made_from_a_layout_takes_the_look_of_its_sample_text():
    """A layout styled on its sample text, as LibreOffice saves it, gives that look to new text."""
    deck = pptx.Presentation()
    deck.slides.add_slide(deck.slide_layouts[0])
    sample = deck.slide_layouts.get_by_name("Title Only").placeholders[0].text_frame
    sample.text = "Titre"
    sample.paragraphs[0].runs[0].font.size = Pt(40)
    sample.paragraphs[0].runs[0].font.color.theme_color = MSO_THEME_COLOR.ACCENT_6
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(layout="Title Only", texts={2: "Chapitre"})]
    )

    slide = pptx.Presentation(
        BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
    ).slides[0]
    run = slide.shapes.title.text_frame.paragraphs[0].runs[0]
    assert run.font.size == Pt(40)
    assert run.font.color.theme_color == MSO_THEME_COLOR.ACCENT_6


def test_the_sections_and_custom_shows_listing_the_user_slides_are_dropped():
    """They list the user's slides, not the copies: a dropped slide goes, from the file too."""
    deck = pptx.Presentation()
    kept = deck.slides.add_slide(deck.slide_layouts[5])
    kept.shapes.title.text = "Gardée"
    dropped = deck.slides.add_slide(deck.slide_layouts[5])
    dropped.shapes.title.text = "Confidentiel"
    presentation_xml = deck.part._element  # pylint: disable=protected-access
    slide_ids = list(deck.slides._sldIdLst)  # pylint: disable=protected-access
    namespaces = (
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"'
    )
    presentation_xml.find(qn("p:notesSz")).addnext(
        parse_xml(
            f'<p:custShowLst {namespaces}><p:custShow name="Courte" id="0"><p:sldLst>'
            f'<p:sld r:id="{slide_ids[1].rId}"/></p:sldLst></p:custShow></p:custShowLst>'
        )
    )
    presentation_xml.append(
        parse_xml(
            f'<p:extLst {namespaces}><p:ext uri="{{521415D9-36F7-43E2-AB2F-B90AF26B5E84}}">'
            '<p14:sectionLst><p14:section name="Partie" '
            'id="{00000000-0000-0000-0000-000000000001}"><p14:sldIdLst>'
            + "".join(f'<p14:sldId id="{slide_id.id}"/>' for slide_id in slide_ids)
            + "</p14:sldIdLst></p14:section></p14:sectionLst></p:ext></p:extLst>"
        )
    )
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(title="Deck", slides=[TemplatedSlide(template_slide=1)])

    output = build_from_template(blob.getvalue(), presentation, PresentationStyle())

    parts = file_parts(output)
    assert b"custShowLst" not in parts["ppt/presentation.xml"]
    assert b"sectionLst" not in parts["ppt/presentation.xml"]
    assert not any(b"onfidentiel" in content for content in parts.values())
    assert texts(pptx.Presentation(BytesIO(output)).slides[0]) == ["Gardée"]


def test_a_picture_background_and_a_colour_map_are_copied():
    """
    The background of a copy points to the picture of the user's slide, and
    the copy keeps the slide's own mapping of the theme colours.
    """
    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    # Notes come first, and are not related the same way to the copy: its ids differ.
    slide.notes_slide.notes_text_frame.text = "Note"
    _image_part, image_id = slide.part.get_or_add_image_part(BytesIO(PICTURE.read_bytes()))
    background = OxmlElement("p:bg")
    properties = OxmlElement("p:bgPr")
    fill = OxmlElement("a:blipFill")
    picture = OxmlElement("a:blip")
    picture.set(qn("r:embed"), image_id)
    fill.append(picture)
    fill.append(OxmlElement("a:stretch"))
    properties.append(fill)
    properties.append(OxmlElement("a:effectLst"))
    background.append(properties)
    slide._element.cSld.insert(0, background)  # pylint: disable=protected-access
    slide._element.replace(  # pylint: disable=protected-access
        slide._element.find(qn("p:clrMapOvr")),  # pylint: disable=protected-access
        parse_xml(
            '<p:clrMapOvr xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:overrideClrMapping bg1="dk1" tx1="lt1" bg2="dk2" tx2="lt2" accent1="accent1" '
            'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
            'accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr>'
        ),
    )
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(title="Deck", slides=[TemplatedSlide(template_slide=1)])

    copy = pptx.Presentation(
        BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
    ).slides[0]

    blip = copy._element.cSld.bg.find(f".//{qn('a:blip')}")  # pylint: disable=protected-access
    assert copy.part.related_part(blip.get(qn("r:embed"))).content_type == "image/png"
    color_maps = copy._element.findall(qn("p:clrMapOvr"))  # pylint: disable=protected-access
    assert len(color_maps) == 1
    assert color_maps[0][0].get("bg1") == "dk1"


def test_an_empty_title_takes_a_layout_title_without_a_list_style():
    """A layout title saved without its optional list style still gives a copy its look."""
    deck = pptx.Presentation()
    layout = deck.slide_layouts.get_by_name("Title Only")
    title = layout.placeholders[0]._element  # pylint: disable=protected-access
    title.txBody.remove(title.txBody.find(qn("a:lstStyle")))
    deck.slides.add_slide(layout)
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(template_slide=1, texts={2: "Chapitre"})]
    )

    slide = pptx.Presentation(
        BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
    ).slides[0]

    assert slide.shapes.title.text_frame.text == "Chapitre"


def test_hidden_slides_and_content_copies_leave_out_are_told():
    """
    The agent is told which slides are hidden, as their copies stay, and which hold
    content that copies leave out, such as an equation.
    """
    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Annexe"
    slide._element.set("show", "false")  # pylint: disable=protected-access
    slide.shapes._spTree.append(  # pylint: disable=protected-access
        parse_xml(
            '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/'
            'markup-compatibility/2006"><mc:Fallback/></mc:AlternateContent>'
        )
    )
    blob = BytesIO()
    deck.save(blob)

    description = outline_template(blob.getvalue()).description
    assert "Slide 1 (hidden), layout 'Title Only':" in description
    assert "- also holds: content that copies leave out" in description
    presentation = TemplatedPresentation(title="Deck", slides=[TemplatedSlide(template_slide=1)])
    built = pptx.Presentation(
        BytesIO(build_from_template(blob.getvalue(), presentation, PresentationStyle()))
    )
    assert built.slides[0]._element.get("show") == "0"  # pylint: disable=protected-access


def test_the_slides_a_deck_drops_do_not_stay_inside_its_file():
    """
    A copied slide linking to a dropped one, as a clickable agenda does, does not
    keep it, nor does the outline view, nor do the file's metadata keep its title
    or who wrote, reviewed, co-edited it or got it shared; and nothing left links
    to what was dropped.
    """
    deck = pptx.Presentation()
    agenda = deck.slides.add_slide(deck.slide_layouts[5])
    agenda.shapes.title.text = "Sommaire"
    dropped = deck.slides.add_slide(deck.slide_layouts[5])
    dropped.shapes.title.text = "Confidentiel"
    dropped.notes_slide.notes_text_frame.text = "Note confidentielle"
    link = agenda.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(2), Inches(2), Inches(1))
    link.click_action.target_slide = dropped
    deck.core_properties.author = "Agent du ministère"
    # PowerPoint lists the slide titles and the company in the application properties,
    # and keeps the reviewers' names apart from their comments.
    package = deck.part.package
    app = next(
        rel.target_part
        for rel in package._rels.values()  # pylint: disable=protected-access
        if rel.reltype == RT.EXTENDED_PROPERTIES
    )
    app._blob = (  # pylint: disable=protected-access
        b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        b'extended-properties"><Company>Agence</Company><TitlesOfParts>Confidentiel'
        b"</TitlesOfParts></Properties>"
    )
    authors = Part(
        PackURI("/ppt/commentAuthors.xml"),
        CT.PML_COMMENT_AUTHORS,
        package,
        b'<p:cmAuthorLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        b'<p:cmAuthor id="1" name="Relectrice" initials="R" lastIdx="1" clrIdx="0"/>'
        b"</p:cmAuthorLst>",
    )
    deck.part.relate_to(authors, RT.COMMENT_AUTHORS)
    # Co-authoring keeps who edited each slide, and custom properties may name an owner.
    changes = Part(
        PackURI("/ppt/changesInfos/changesInfo1.xml"),
        "application/vnd.ms-powerpoint.changesinfo+xml",
        package,
        b'<pc:chInfo xmlns:pc="http://schemas.microsoft.com/office/powerpoint/2013/main/command">'
        b'<pc:docChgLst><pc:chgData name="Coredactrice" userId="S::x@y"/></pc:docChgLst>'
        b"</pc:chInfo>",
    )
    deck.part.relate_to(
        changes, "http://schemas.microsoft.com/office/2016/11/relationships/changesInfo"
    )
    custom = Part(
        PackURI("/docProps/custom.xml"),
        CT.OFC_CUSTOM_PROPERTIES,
        package,
        b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        b'custom-properties"><property name="Owner">Proprietaire</property></Properties>',
    )
    package.relate_to(custom, RT.CUSTOM_PROPERTIES)
    shared_with = Part(
        PackURI("/customXml/item1.xml"),
        "application/xml",
        package,
        b"<p:properties><UserInfo><DisplayName>Destinataire</DisplayName></UserInfo>"
        b"</p:properties>",
    )
    deck.part._element.find(qn("p:defaultTextStyle")).addprevious(  # pylint: disable=protected-access
        parse_xml(
            '<p:custDataLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<p:custData r:id="{deck.part.relate_to(shared_with, RT.CUSTOM_XML)}"/>'
            "</p:custDataLst>"
        )
    )
    # The outline view lists its collapsed slides.
    view = deck.part.part_related_by(RT.VIEW_PROPS)
    view_rel = view.relate_to(dropped.part, RT.SLIDE)
    view._blob = (  # pylint: disable=protected-access
        b'<p:viewPr xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        b'<p:outlineViewPr><p:cViewPr><p:origin x="0" y="0"/></p:cViewPr><p:sldLst>'
        b'<p:sld r:id="' + view_rel.encode() + b'" collapse="1"/></p:sldLst></p:outlineViewPr>'
        b"</p:viewPr>"
    )
    blob = BytesIO()
    deck.save(blob)
    presentation = TemplatedPresentation(title="Deck", slides=[TemplatedSlide(template_slide=1)])

    output = build_from_template(blob.getvalue(), presentation, PresentationStyle())

    parts = file_parts(output)
    for leak in (
        b"onfidentiel",
        b"Agence",
        b"Relectrice",
        b"Coredactrice",
        b"Proprietaire",
        b"Destinataire",
    ):
        assert not any(leak in content for content in parts.values()), leak
    assert "docProps/thumbnail.jpeg" not in parts
    assert not dangling_links(parts)
    built = pptx.Presentation(BytesIO(output))
    assert built.core_properties.author == ""
    assert built.core_properties.title == "Deck"


def test_each_copy_of_a_chart_slide_gets_its_own_chart(monkeypatch):
    """
    PowerPoint asks to repair a deck whose slides share a chart, and blanks one
    of them. Copies are refused past a size, a chart's workbook being heavy.
    """
    presentation = TemplatedPresentation(
        title="Deck", slides=[TemplatedSlide(template_slide=1), TemplatedSlide(template_slide=1)]
    )

    output = build_from_template(
        deck_with_table_group_and_chart(), presentation, PresentationStyle()
    )

    charts = [
        next(shape for shape in slide.shapes if shape.has_chart).chart_part
        for slide in pptx.Presentation(BytesIO(output)).slides
    ]
    assert charts[0].partname != charts[1].partname
    workbooks = [chart.chart_workbook.xlsx_part for chart in charts]
    assert workbooks[0].partname != workbooks[1].partname
    assert workbooks[0].blob == workbooks[1].blob
    assert not dangling_links(file_parts(output))

    monkeypatch.setattr(from_template, "MAX_COPIED_SIZE", len(workbooks[0].blob))
    with pytest.raises(TemplateTooLargeError):
        build_from_template(deck_with_table_group_and_chart(), presentation, PresentationStyle())
