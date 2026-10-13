"""Load CSV/XLSX attachments into pandas DataFrames and query them with a validated spec.

LLMs cannot reliably count or sum rows read from their context, so spreadsheet
attachments are analyzed by code instead. The model never writes code: it fills a
structured query (`TableQuery`: filters, grouping, aggregations, sort, join) that
is validated by pydantic and executed here with pandas. Runs inside a Celery
worker (`run_tabular_query_task`).

The loader does its own type inference so French-formatted files work: decimal
commas (`1 234,56`), `;` separators, cp1252 encoding and `dd/mm/yyyy` dates.
"""

import csv
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import PurePath
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field
from python_calamine import CalamineWorkbook, SheetTypeEnum

from chat.agent_rag.document_converter.guards import guard_zip_bomb
from chat.constants import XLSX_MIME_TYPE

logger = logging.getLogger(__name__)

CSV_DELIMITERS = (",", ";", "\t", "|")
MAX_CELL_DISPLAY_LENGTH = 200
SAMPLE_ROWS = 3
# Integers longer than this are identifiers (SIRET, phone numbers...), not quantities.
MAX_INTEGER_DIGITS = 15
NUMERIC_AGGREGATIONS = frozenset({"sum", "mean", "median"})

# Thousands groups separated by a space or the "other" separator, then an optional fraction.
_NUMBER_PATTERNS = {
    ",": re.compile(r"[+-]?(\d{1,3}(?:[ .]\d{3})+|\d+)(,\d+)?"),
    ".": re.compile(r"[+-]?(\d{1,3}(?:[ ,]\d{3})+|\d+)(\.\d+)?"),
}
_FR_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?")
_SPACES = str.maketrans({"\u00a0": " ", "\u202f": " "})


class TabularError(Exception):
    """A user-facing error: unreadable file or invalid query. The message goes to the model."""


@dataclass
class TabularFile:
    """A spreadsheet attachment read from storage."""

    file_name: str
    content_type: str
    content: bytes


@dataclass
class Column:
    """A loaded column: identifier, header as written in the file, inferred type."""

    name: str
    header: str
    kind: str  # integer, real, date, text


@dataclass
class Table:
    """A loaded table and where it comes from."""

    name: str
    source: str
    columns: list[Column]
    row_count: int


@dataclass
class TabularDataset:
    """The tables loaded from the conversation's spreadsheets."""

    tables: list[Table] = field(default_factory=list)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


class Filter(BaseModel):
    """A condition on one column. Several filters are combined with AND."""

    column: str
    op: Literal["==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains", "is_null", "not_null"]
    value: str | int | float | list[str | int | float] | None = Field(
        default=None,
        description=(
            "Value to compare with; a list for in/not_in; omitted for is_null/not_null. "
            "Dates as YYYY-MM-DD."
        ),
    )


class GroupKey(BaseModel):
    """A grouping column, optionally truncated to a period for date columns."""

    column: str
    period: Literal["year", "quarter", "month"] | None = Field(
        default=None, description="Only for date columns: group by year, quarter or month."
    )


class Aggregation(BaseModel):
    """An aggregate computed per group (or over all rows without group_by)."""

    func: Literal["count", "sum", "mean", "median", "min", "max", "nunique"]
    column: str | None = Field(
        default=None, description="Column to aggregate. Omit with func=count to count rows."
    )


class SortKey(BaseModel):
    """A sort column of the result (an aggregate is named <column>_<func>, or count)."""

    column: str
    descending: bool = False


class Join(BaseModel):
    """An inner join of the main table with another table."""

    table: str
    left_on: str = Field(description="Column of the main table.")
    right_on: str = Field(description="Column of the joined table.")


class TableQuery(BaseModel):
    """A structured query on one table: join, filter, group/aggregate, select, sort, limit."""

    table: str
    join: Join | None = None
    filters: list[Filter] = Field(default_factory=list)
    group_by: list[GroupKey] = Field(default_factory=list)
    aggregations: list[Aggregation] = Field(default_factory=list)
    columns: list[str] = Field(
        default_factory=list,
        description="Columns to return when not aggregating. All columns when empty.",
    )
    sort: list[SortKey] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=100)


def _identifier(raw, fallback: str) -> str:
    """Turn a header or file name into a lowercase ASCII identifier."""
    text = unicodedata.normalize("NFKD", str(raw or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower() or fallback
    return f"c_{text}" if text[0].isdigit() else text


def _unique(name: str, taken: set[str]) -> str:
    """Suffix `name` until it is not in `taken`, then reserve it."""
    candidate, index = name, 2
    while candidate in taken:
        candidate, index = f"{name}_{index}", index + 1
    taken.add(candidate)
    return candidate


def _parse_number(text: str, decimal_separator: str) -> int | float | None:
    """Parse a formatted number, or return None when `text` is not one."""
    match = _NUMBER_PATTERNS[decimal_separator].fullmatch(text.translate(_SPACES))
    if not match:
        return None
    digits = re.sub(r"[ .,]", "", match.group(1))
    fraction = match.group(2)
    if fraction is None and len(digits) > 1 and digits.startswith("0"):
        return None  # leading zero: a code (postal code, ...), keep it as text
    if len(digits) > MAX_INTEGER_DIGITS:
        return None
    sign = "-" if text.startswith("-") else ""
    if fraction is None:
        return int(sign + digits)
    return float(f"{sign}{digits}.{fraction[1:]}")


def _to_number(value, decimal_separator: str) -> int | float | None:
    """Convert a cell to a number: native numbers pass through, strings are parsed."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return _parse_number(value, decimal_separator)


def _to_iso_date(value) -> str | None:
    """Convert a `dd/mm/yyyy` or ISO date (optionally with time) to ISO text."""
    if not isinstance(value, str):
        return None
    if _ISO_DATE.fullmatch(value):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return None
        return value
    match = _FR_DATE.fullmatch(value)
    if not match:
        return None
    day, month, year, hour, minute, second = match.groups()
    try:
        parsed = datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0)
        )
    except ValueError:
        return None
    return parsed.date().isoformat() if hour is None else parsed.isoformat(sep=" ")


def _convert_column(values: list, converter) -> list | None:
    """Apply `converter` to every non-null value, or return None if one fails."""
    converted = []
    for value in values:
        if value is None:
            converted.append(None)
            continue
        result = converter(value)
        if result is None:
            return None
        converted.append(result)
    return converted


def _infer_column(values: list, decimal_order: tuple[str, ...]) -> tuple[str, list]:
    """Pick the narrowest type that fits every value of a column, and convert it."""
    if any(value is not None for value in values):
        for decimal_separator in decimal_order:
            numbers = _convert_column(values, lambda v, d=decimal_separator: _to_number(v, d))
            if numbers is not None:
                is_integer = all(isinstance(n, int) for n in numbers if n is not None)
                return ("integer" if is_integer else "real"), numbers
        dates = _convert_column(values, _to_iso_date)
        if dates is not None:
            return "date", dates
    return "text", [None if value is None else str(value) for value in values]


def _normalize_cell(value):
    """Map a raw cell to None, a native number, or stripped text."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bool, int, float)):
        return value
    text = str(value).strip()
    return text or None


def _decode(content: bytes) -> str:
    """Decode CSV bytes: UTF-8 (with or without BOM), else cp1252, else latin-1."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")


def _read_csv(content: bytes) -> tuple[list[list], tuple[str, ...]]:
    """Read CSV rows, guessing the delimiter from the header line."""
    text = _decode(content)
    header_line = text.split("\n", 1)[0]
    delimiter = max(CSV_DELIMITERS, key=header_line.count)
    if header_line.count(delimiter) == 0:
        delimiter = ","
    rows = [
        [_normalize_cell(cell) for cell in row]
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
    ]
    # A `;` separator is the French convention, where the decimal separator is a comma.
    decimal_order = (",", ".") if delimiter == ";" else (".", ",")
    return rows, decimal_order


def _excel_cell(value):
    """Normalize a calamine cell: it returns every number as a float, 1 as 1.0."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return _normalize_cell(value)


def _read_xlsx(content: bytes) -> list[tuple[str, list[list]]]:
    """Read every worksheet (charts skipped) as (sheet name, rows).

    Formulas give their last calculated value, empty when the file never stored one.
    """
    guard_zip_bomb(content)
    with CalamineWorkbook.from_filelike(io.BytesIO(content)) as workbook:
        return [
            (
                sheet.name,
                [
                    [_excel_cell(cell) for cell in row]
                    for row in workbook.get_sheet_by_name(sheet.name).to_python()
                ],
            )
            for sheet in workbook.sheets_metadata
            if sheet.typ == SheetTypeEnum.WorkSheet
        ]


def _build_frame(
    name: str, source: str, rows: list[list], decimal_order: tuple[str, ...]
) -> tuple[Table, pd.DataFrame] | None:
    """Build a typed DataFrame from rows whose first non-empty row is the header."""
    rows = [row for row in rows if any(cell is not None for cell in row)]
    if not rows:
        return None
    header, data = rows[0], rows[1:]
    width = max(len(row) for row in rows)
    taken: set[str] = set()
    headers = [header[i] if i < len(header) else None for i in range(width)]
    names = [_unique(_identifier(h, f"column_{i + 1}"), taken) for i, h in enumerate(headers)]

    raw_columns = [[row[i] if i < len(row) else None for row in data] for i in range(width)]
    kinds, values = zip(
        *(_infer_column(column, decimal_order) for column in raw_columns), strict=True
    )
    dtypes = {"integer": "Int64", "real": "Float64", "text": "object"}
    frame = pd.DataFrame(
        {
            column: (
                pd.to_datetime(pd.Series(column_values, dtype="object"))
                if kind == "date"
                else pd.Series(column_values, dtype=dtypes[kind])
            )
            for column, kind, column_values in zip(names, kinds, values, strict=True)
        }
    )
    table = Table(
        name=name,
        source=source,
        columns=[
            Column(name=n, header="" if h is None else str(h), kind=k)
            for n, h, k in zip(names, headers, kinds, strict=True)
        ],
        row_count=len(data),
    )
    return table, frame


def build_dataset(files: list[TabularFile]) -> TabularDataset:
    """Load the files into DataFrames, one per CSV file or Excel sheet.

    A file that cannot be read is skipped (listed in `skipped`) so the others
    stay queryable.
    """
    dataset = TabularDataset()
    taken: set[str] = set()
    for file in files:
        stem = _identifier(PurePath(file.file_name).stem, "table")
        try:
            if file.content_type == XLSX_MIME_TYPE:
                sheets = _read_xlsx(file.content)
                sources = [
                    (
                        f"{stem}_{_identifier(title, 'sheet')}" if len(sheets) > 1 else stem,
                        f"{file.file_name} (sheet {title})",
                        rows,
                        (",", "."),
                    )
                    for title, rows in sheets
                ]
            else:
                rows, decimal_order = _read_csv(file.content)
                sources = [(stem, file.file_name, rows, decimal_order)]
            for name, source, rows, decimal_order in sources:
                built = _build_frame(_unique(name, taken), source, rows, decimal_order)
                if built is not None:
                    table, frame = built
                    dataset.tables.append(table)
                    dataset.frames[table.name] = frame
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            logger.warning("Could not load spreadsheet %s", file.file_name, exc_info=True)
            dataset.skipped.append(file.file_name)
    return dataset


def _format_cell(value) -> str:
    """Render a value for a markdown table cell."""
    if value is None or (not isinstance(value, (list, tuple)) and pd.isna(value)):
        return ""
    if isinstance(value, pd.Timestamp):
        text = value.date().isoformat() if value == value.normalize() else str(value)
    elif isinstance(value, float):
        text = f"{round(value, 4):.4f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    text = text.replace("|", "\\|").replace("\n", " ")
    if len(text) > MAX_CELL_DISPLAY_LENGTH:
        return text[:MAX_CELL_DISPLAY_LENGTH] + "…"
    return text


def _markdown_table(columns: list[str], rows) -> str:
    """Render rows as a markdown table."""
    lines = [
        "| " + " | ".join(_format_cell(c) for c in columns) + " |",
        "|" + "---|" * len(columns),
    ]
    lines.extend("| " + " | ".join(_format_cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def _frame(dataset: TabularDataset, name: str) -> pd.DataFrame:
    """Return a table's DataFrame, or tell the model which tables exist."""
    if name not in dataset.frames:
        raise TabularError(
            f'Unknown table "{name}". Available tables: {", ".join(dataset.frames) or "none"}.'
        )
    return dataset.frames[name]


def _check_columns(frame: pd.DataFrame, columns, where: str) -> None:
    """Raise with the list of valid columns when one does not exist."""
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise TabularError(
            f"Unknown column(s) {', '.join(missing)} in {where}. "
            f"Available columns: {', '.join(frame.columns)}."
        )


def _coerce(series: pd.Series, value):
    """Convert a filter value to the column's type (dates given as text)."""
    if pd.api.types.is_datetime64_any_dtype(series):
        if isinstance(value, list):
            return [pd.Timestamp(v) for v in value]
        return pd.Timestamp(value)
    return value


def _mask(frame: pd.DataFrame, condition: Filter) -> pd.Series:
    """Boolean mask of the rows matching one filter."""
    series = frame[condition.column]
    if condition.op == "is_null":
        return series.isna()
    if condition.op == "not_null":
        return series.notna()
    if condition.value is None:
        raise TabularError(f'Filter on "{condition.column}" with op {condition.op} needs a value.')
    value = _coerce(series, condition.value)
    if condition.op in ("in", "not_in"):
        values = value if isinstance(value, list) else [value]
        mask = series.isin(values)
        return ~mask if condition.op == "not_in" else mask
    if condition.op == "contains":
        return (
            series.astype("string")
            .str.contains(str(condition.value), case=False, regex=False)
            .fillna(False)
            .astype(bool)
        )
    comparisons = {
        "==": series.__eq__,
        "!=": series.__ne__,
        ">": series.__gt__,
        ">=": series.__ge__,
        "<": series.__lt__,
        "<=": series.__le__,
    }
    return comparisons[condition.op](value).fillna(False).astype(bool)


def _group_keys(frame: pd.DataFrame, group_by: list[GroupKey]) -> tuple[pd.DataFrame, list[str]]:
    """Add period columns for date grouping; return the frame and the key column names."""
    keys = []
    for key in group_by:
        if key.period is None:
            keys.append(key.column)
            continue
        series = frame[key.column]
        if not pd.api.types.is_datetime64_any_dtype(series):
            raise TabularError(f'"{key.column}" is not a date column: it cannot use a period.')
        name = f"{key.column}_{key.period}"
        if key.period == "year":
            frame = frame.assign(**{name: series.dt.year})
        else:
            frame = frame.assign(
                **{name: series.dt.to_period("Q" if key.period == "quarter" else "M").astype(str)}
            )
        keys.append(name)
    return frame, keys


def _aggregate(frame: pd.DataFrame, query: TableQuery) -> pd.DataFrame:
    """Compute the aggregations, per group when group_by is set."""
    _check_columns(frame, [key.column for key in query.group_by], "group_by")
    frame, keys = _group_keys(frame, query.group_by)
    results = {}
    for aggregation in query.aggregations or [Aggregation(func="count")]:
        if aggregation.column is None:
            if aggregation.func != "count":
                raise TabularError(f"Aggregation {aggregation.func} needs a column.")
            results["count"] = frame.groupby(keys, dropna=False).size() if keys else len(frame)
            continue
        _check_columns(frame, [aggregation.column], "aggregations")
        if aggregation.func in NUMERIC_AGGREGATIONS and not pd.api.types.is_numeric_dtype(
            frame[aggregation.column]
        ):
            raise TabularError(
                f'"{aggregation.column}" is not numeric: {aggregation.func} is not possible.'
            )
        source = (
            frame.groupby(keys, dropna=False)[aggregation.column]
            if keys
            else frame[aggregation.column]
        )
        results[f"{aggregation.column}_{aggregation.func}"] = getattr(source, aggregation.func)()
    if not keys:
        return pd.DataFrame([results])
    return pd.concat(results, axis=1).reset_index()


def run_table_query(dataset: TabularDataset, query: TableQuery, max_rows: int) -> str:
    """Execute a validated query and return the result as a markdown table.

    Raises:
        TabularError: unknown table or column, or an operation the column type forbids.
    """
    frame = _frame(dataset, query.table)
    if query.join is not None:
        other = _frame(dataset, query.join.table)
        _check_columns(frame, [query.join.left_on], f'table "{query.table}"')
        _check_columns(other, [query.join.right_on], f'table "{query.join.table}"')
        frame = frame.merge(
            other,
            how="inner",
            left_on=query.join.left_on,
            right_on=query.join.right_on,
            suffixes=("", f"_{query.join.table}"),
        )
    _check_columns(frame, [condition.column for condition in query.filters], "filters")
    try:
        for condition in query.filters:
            frame = frame[_mask(frame, condition)]
        if query.group_by or query.aggregations:
            result = _aggregate(frame, query)
        else:
            _check_columns(frame, query.columns, "columns")
            result = frame[query.columns] if query.columns else frame
        _check_columns(result, [key.column for key in query.sort], "sort")
        if query.sort:
            result = result.sort_values(
                by=[key.column for key in query.sort],
                ascending=[not key.descending for key in query.sort],
            )
    except (TypeError, ValueError) as exc:
        raise TabularError(f"Invalid query: {exc}") from exc

    total = len(result)
    if total == 0:
        return "The query returned no rows."
    shown = result.head(min(query.limit, max_rows))
    table = _markdown_table(list(shown.columns), shown.itertuples(index=False))
    if total > len(shown):
        table += f"\n\n{len(shown)} of {total} rows shown."
        if query.limit >= max_rows:
            # Cut by the cap, not by a limit the model chose.
            table += " The list is incomplete: aggregate the data if you need a complete answer."
    return table


def describe_tables(dataset: TabularDataset) -> str:
    """Describe every table: name, source file, row count, columns and sample rows."""
    if not dataset.tables:
        return "No spreadsheet could be loaded from the attachments."
    sections = []
    for table in dataset.tables:
        column_lines = "\n".join(
            f"- {column.name} ({column.kind})"
            + (f' - header in file: "{column.header}"' if column.header != column.name else "")
            for column in table.columns
        )
        sample = dataset.frames[table.name].head(SAMPLE_ROWS)
        sections.append(
            f"## Table {table.name}\n"
            f"Source: {table.source}\n"
            f"Rows: {table.row_count}\n"
            f"Columns:\n{column_lines}\n\n"
            f"Sample rows:\n"
            f"{_markdown_table(list(sample.columns), sample.itertuples(index=False))}"
        )
    if dataset.skipped:
        sections.append("These files could not be read: " + ", ".join(dataset.skipped))
    return "\n\n".join(sections)
