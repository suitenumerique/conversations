"""Binding of the bundled generic template to the slide types.

The pptx file carries the visual identity (colour scheme, Marianne typeface,
masters and layout geometry); this module only declares which placeholder of
which layout receives which field.

Layout names are French because they are what a user sees in the layout picker
once the deck is opened in PowerPoint or Impress.

Two placeholder choices look surprising and are deliberate: in `Couverture` and
`Titre et sous-titre` the `Title 1` shape is a degenerate 0.2 inch box, so the
visible block is the one at index 1, which is why the cover title is mapped
there and the `Couverture` layout is left unused.
"""

from pathlib import Path

from chat.file_generation.entities import PresentationTemplate, SlideLayout, SlideType

TEMPLATE_PATH = Path(__file__).parent / "generic.pptx"


GENERIC_TEMPLATE = PresentationTemplate(
    path=TEMPLATE_PATH,
    layouts=(
        SlideLayout(
            slide_type=SlideType.COVER,
            layout_name="Titre et sous-titre",
            shape_index_to_field={1: "title"},
            prompt="Cover slide with one large block for the deck title. Fields: title",
        ),
        SlideLayout(
            slide_type=SlideType.SECTION,
            layout_name="Chapitre",
            shape_index_to_field={1: "title", 0: "subtitle"},
            prompt="Section divider slide. Fields: title, subtitle",
        ),
        SlideLayout(
            slide_type=SlideType.TITLE_ONE_COLUMN,
            layout_name="Titre et textes 1 colonne",
            shape_index_to_field={0: "title", 1: "content"},
            prompt="Slide with a title and a single large body block. Fields: title, content",
        ),
        SlideLayout(
            slide_type=SlideType.TITLE_TWO_COLUMNS,
            layout_name="Titre et textes 2 colonnes",
            shape_index_to_field={0: "title", 1: "left", 3: "right"},
            prompt=("Slide with a title and two side-by-side blocks. Fields: title, left, right"),
        ),
        SlideLayout(
            slide_type=SlideType.TITLE_THREE_COLUMNS,
            layout_name="Titre et textes 3 colonnes",
            shape_index_to_field={0: "title", 2: "left", 3: "center", 4: "right"},
            prompt=(
                "Slide with a title and three side-by-side blocks. "
                "Fields: title, left, center, right"
            ),
        ),
    ),
)
