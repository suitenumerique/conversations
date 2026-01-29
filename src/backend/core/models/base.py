"""
Declare and configure base models for the conversations core application
"""
from django.db import models
import uuid
from django.utils.translation import gettext_lazy as _

class BaseModel(models.Model):
    """
    Serves as an abstract base model for other models, ensuring that records are validated
    before saving as Django doesn't do it by default.

    Includes fields common to all models: a UUID primary key and creation/update timestamps.
    """

    id = models.UUIDField(
        verbose_name=_("id"),
        help_text=_("primary key for the record as UUID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(
        verbose_name=_("created on"),
        help_text=_("date and time at which a record was created"),
        auto_now_add=True,
        editable=False,
    )
    updated_at = models.DateTimeField(
        verbose_name=_("updated on"),
        help_text=_("date and time at which a record was last updated"),
        auto_now=True,
        editable=False,
    )

    class Meta:  # pylint:disable=missing-class-docstring
        abstract = True

    def save(self, *args, **kwargs):
        """Call `full_clean` before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

