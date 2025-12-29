"""API filters for Conversations' core application."""

import unicodedata


def remove_accents(value):
    """Remove accents from a string (vélo -> velo)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )
