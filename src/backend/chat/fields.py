"""Model fields for the chat application."""

from django.db import models

from django_pydantic_field.fields import PydanticSchemaField


def strip_nul(value):
    """Remove NUL characters from strings nested in a JSON-like value.

    Postgres jsonb rejects the `\\u0000` escape, so a single NUL coming from a
    parsed document or a model output would fail the whole save.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {strip_nul(key): strip_nul(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [strip_nul(item) for item in value]
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


# pylint cannot resolve the MRO of the generic PydanticSchemaField.
class NulSafeSchemaField(PydanticSchemaField):  # pylint: disable=inconsistent-mro
    """Pydantic SchemaField that can store values containing NUL characters.

    Hooks `get_prep_value` like `NulSafeJSONField`, so every write is covered.
    """

    def get_prep_value(self, value):
        """Prepare the value as SchemaField does, then strip NUL characters."""
        return strip_nul(super().get_prep_value(value))
