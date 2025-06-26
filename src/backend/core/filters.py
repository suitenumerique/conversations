"""API filters for Conversations' core application."""

import unicodedata

import django_filters


def remove_accents(value):
    """Remove accents from a string (vélo -> velo)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )


class AccentInsensitiveCharFilter(django_filters.CharFilter):
    """
    A custom CharFilter that filters on the accent-insensitive value searched.
    """

    def filter(self, qs, value):
        """
        Apply the filter to the queryset using the unaccented version of the field.

        Args:
            qs: The queryset to filter.
            value: The value to search for in the unaccented field.
        Returns:
            A filtered queryset.
        """
        if value:
            value = remove_accents(value)
        return super().filter(qs, value)
