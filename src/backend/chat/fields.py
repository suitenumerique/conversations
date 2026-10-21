"""Model fields for the chat application."""

from django.db import models

from django_pydantic_field.fields import PydanticSchemaField


def has_nul(value):
    """Tell whether a JSON-like value holds a NUL character in any string."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(has_nul(key) or has_nul(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(has_nul(item) for item in value)
    return False


def strip_nul(value):
    """Remove NUL characters from strings nested in a JSON-like value.

    Postgres jsonb rejects the `\\u0000` escape, so a single NUL coming from a
    parsed document or a model output would fail the whole save. Values without
    NUL, the usual case, are returned as is rather than rebuilt.
    """
    return _remove_nul(value) if has_nul(value) else value


def _remove_nul(value):
    """Rebuild a JSON-like value with NUL characters removed from its strings."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {_remove_nul(key): _remove_nul(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_remove_nul(item) for item in value]
    return value


class NulSafeJSONField(models.JSONField):
    """JSONField that can store values containing NUL characters.

    Hooking `get_prep_value` covers every write: `save`, `create`,
    `bulk_create` and `QuerySet.update`.
    """

    def get_prep_value(self, value):
        """Prepare the value as JSONField does, then strip NUL characters."""
        # pylint-django hides `Field.get_prep_value` from inference.
        return strip_nul(super().get_prep_value(value))  # pylint: disable=no-member


class NulSafeCharField(models.CharField):
    """CharField that can store values containing NUL characters.

    Postgres text columns reject NUL; hooks `get_prep_value` like `NulSafeJSONField`.
    """

    def get_prep_value(self, value):
        """Prepare the value as CharField does, then strip NUL characters."""
        return strip_nul(super().get_prep_value(value))  # pylint: disable=no-member


class NulSafeTextField(models.TextField):
    """TextField that can store values containing NUL characters.

    Postgres text columns reject NUL; hooks `get_prep_value` like `NulSafeJSONField`.
    """

    def get_prep_value(self, value):
        """Prepare the value as TextField does, then strip NUL characters."""
        return strip_nul(super().get_prep_value(value))  # pylint: disable=no-member


# pylint cannot resolve the MRO of the generic PydanticSchemaField.
class NulSafeSchemaField(PydanticSchemaField):  # pylint: disable=inconsistent-mro
    """Pydantic SchemaField that can store values containing NUL characters.

    Hooks `get_prep_value` like `NulSafeJSONField`, so every write is covered.
    """

    def get_prep_value(self, value):
        """Prepare the value as SchemaField does, then strip NUL characters."""
        return strip_nul(super().get_prep_value(value))
