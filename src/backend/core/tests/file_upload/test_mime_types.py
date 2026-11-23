"""Tests for content-type resolution helpers."""

import pytest

from core.file_upload.mime_types import resolve_csv_content_type


@pytest.mark.parametrize(
    "file_name,content_type",
    [
        ("ventes.csv", "text/plain"),
        ("VENTES.CSV", "text/plain"),
        ("ventes.csv", "application/vnd.ms-excel"),
        ("ventes.csv", "application/octet-stream"),
        ("ventes.csv", ""),
        ("ventes.csv", None),
        ("ventes.csv", "text/csv"),
    ],
)
def test_resolve_csv_content_type_trusts_csv_name(file_name, content_type):
    """A .csv file with a generic or missing type is text/csv."""
    assert resolve_csv_content_type(file_name, content_type) == "text/csv"


@pytest.mark.parametrize(
    "file_name,content_type,expected",
    [
        ("notes.txt", "text/plain", "text/plain"),
        ("fake.csv", "image/png", "image/png"),
        ("fake.csv", "application/x-dosexec", "application/x-dosexec"),
        (None, "text/plain", "text/plain"),
        ("archive.csv.zip", "application/zip", "application/zip"),
    ],
)
def test_resolve_csv_content_type_keeps_other_types(file_name, content_type, expected):
    """Other files, and .csv files with a specific detected type, keep their type."""
    assert resolve_csv_content_type(file_name, content_type) == expected
