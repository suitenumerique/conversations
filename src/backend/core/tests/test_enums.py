"""Tests for enums module."""

import pytest

from core import enums


@pytest.mark.parametrize(
    "code,expected",
    [
        ("fr", "French"),
        ("en", "English"),
        ("fr-CA", "French"),
        ("en-US", "English"),
        ("zz", "zz"),
        ("zz-XX", "zz-xx"),
        ("", ""),
    ],
)
def test_get_language_name(code, expected):
    """Test get_language_name function with various inputs."""
    assert enums.get_language_name(code) == expected
