"""Declarative schema for visual artifacts.

This module defines the *contract* between the LLM and the frontend renderer.
Every artifact is a small, strongly-typed JSON document: a title plus an
ordered list of typed ``blocks`` (stat grid, bar chart, line chart, table,
callout). The model fills this structure; the frontend maps each ``type`` to a
whitelisted React component. No code, HTML, or arbitrary markup ever crosses
the boundary.

Bounds (max number of blocks, series points, table rows, string lengths) are
enforced here so a malformed or oversized model output is rejected before it
reaches the frontend, turning into a ``ModelRetry`` rather than a render-time
crash or a denial-of-service vector.
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

# --- Bounds -----------------------------------------------------------------
# Kept deliberately small: artifacts are summaries, not data dumps.
MAX_BLOCKS = 12
MAX_STAT_ITEMS = 8
MAX_CATEGORIES = 50
MAX_SERIES = 6
MAX_TABLE_ROWS = 100
MAX_TABLE_COLS = 12
MAX_LABEL_LEN = 120
MAX_TEXT_LEN = 2000

Tone = Literal["neutral", "success", "danger", "warning", "info"]

ShortStr = Annotated[str, Field(min_length=1, max_length=MAX_LABEL_LEN)]
LongStr = Annotated[str, Field(min_length=1, max_length=MAX_TEXT_LEN)]


class StatItem(BaseModel):
    """A single headline metric: a big value with a short label."""

    label: ShortStr
    value: ShortStr
    tone: Tone = "neutral"


class Series(BaseModel):
    """A named numeric series for bar/line charts.

    ``data`` aligns by index with the parent block's ``categories``.
    """

    name: ShortStr
    data: Annotated[list[float], Field(min_length=1, max_length=MAX_CATEGORIES)]
    tone: Tone | None = None


class StatGridBlock(BaseModel):
    """A row of headline metrics."""

    type: Literal["stat_grid"] = "stat_grid"
    items: Annotated[list[StatItem], Field(min_length=1, max_length=MAX_STAT_ITEMS)]


class _ChartBlock(BaseModel):
    """Shared fields and series/category validation for charts."""

    title: ShortStr
    categories: Annotated[list[ShortStr], Field(min_length=1, max_length=MAX_CATEGORIES)]
    series: Annotated[list[Series], Field(min_length=1, max_length=MAX_SERIES)]
    value_suffix: Annotated[str, Field(max_length=12)] | None = None

    @model_validator(mode="after")
    def _series_align_with_categories(self) -> "_ChartBlock":
        """Every series must have exactly one value per category."""
        expected = len(self.categories)
        for serie in self.series:
            if len(serie.data) != expected:
                raise ValueError(
                    f"Series '{serie.name}' has {len(serie.data)} values but there "
                    f"are {expected} categories. Each series must align with categories."
                )
        return self


class BarChartBlock(_ChartBlock):
    """Vertical/stacked bar chart."""

    type: Literal["bar_chart"] = "bar_chart"
    stacked: bool = False


class LineChartBlock(_ChartBlock):
    """Line chart (use for trends over an ordered axis)."""

    type: Literal["line_chart"] = "line_chart"


class TableBlock(BaseModel):
    """A simple data table. ``rows`` cells align with ``headers``."""

    type: Literal["table"] = "table"
    title: ShortStr
    headers: Annotated[list[ShortStr], Field(min_length=1, max_length=MAX_TABLE_COLS)]
    rows: Annotated[
        list[Annotated[list[str], Field(max_length=MAX_TABLE_COLS)]],
        Field(min_length=1, max_length=MAX_TABLE_ROWS),
    ]

    @model_validator(mode="after")
    def _rows_match_headers(self) -> "TableBlock":
        """Each row must have exactly as many cells as there are headers."""
        width = len(self.headers)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"Row {index} has {len(row)} cells but there are {width} headers. "
                    "Every row must have one cell per header."
                )
        return self


class CalloutBlock(BaseModel):
    """A short highlighted note (tip, warning, key takeaway)."""

    type: Literal["callout"] = "callout"
    tone: Tone = "info"
    title: ShortStr | None = None
    text: LongStr


Block = Annotated[
    Union[
        StatGridBlock,
        BarChartBlock,
        LineChartBlock,
        TableBlock,
        CalloutBlock,
    ],
    Field(discriminator="type"),
]


class ArtifactSpec(BaseModel):
    """A complete visual artifact: a title and an ordered list of blocks."""

    title: ShortStr
    blocks: Annotated[list[Block], Field(min_length=1, max_length=MAX_BLOCKS)]
