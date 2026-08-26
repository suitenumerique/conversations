"""
Models for the activation codes application.

The activation-code gate has been removed from the application. These models are
kept read-only so the historical record of which user redeemed which code, and
who asked to be notified, stays available.
"""

import secrets
import string

from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel, User


def generate_activation_code():
    """Generate a random 16-character activation code.

    No longer called by the application: kept because the initial migration and the
    `code` field default both reference it.
    """
    alphabet = string.ascii_uppercase + string.digits
    # Remove ambiguous characters
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(16))


class ActivationCode(BaseModel):
    """
    Represents an activation code that was used to activate user accounts.
    """

    code = models.CharField(
        verbose_name=_("activation code"),
        help_text=_("The activation code that users will enter"),
        max_length=50,
        unique=True,
        default=generate_activation_code,
        validators=[
            RegexValidator(
                regex=r"^[A-Z0-9]+$",
                message=_("Code must be alphanumeric and contain no spaces or special characters"),
            )
        ],
    )

    max_uses = models.PositiveIntegerField(
        verbose_name=_("maximum uses"),
        help_text=_("Maximum number of times this code can be used. 0 means unlimited."),
        default=1,
    )

    current_uses = models.PositiveIntegerField(
        verbose_name=_("current uses"),
        help_text=_("Number of times this code has been used"),
        default=0,
        editable=False,
    )

    is_active = models.BooleanField(
        verbose_name=_("active"),
        help_text=_("Whether this code can still be used"),
        default=True,
    )

    expires_at = models.DateTimeField(
        verbose_name=_("expires at"),
        help_text=_("Date and time when this code expires"),
        null=True,
        blank=True,
    )

    description = models.TextField(
        verbose_name=_("description"),
        help_text=_("Internal description or notes about this code"),
        blank=True,
    )

    class Meta:
        db_table = "activation_code"
        verbose_name = _("activation code")
        verbose_name_plural = _("activation codes")
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the activation code."""
        return f"{self.code} ({self.current_uses}/{self.max_uses if self.max_uses > 0 else '∞'})"


class UserActivation(BaseModel):
    """
    Records with user used which activation code and when.
    """

    user = models.OneToOneField(
        User,
        verbose_name=_("user"),
        help_text=_("The user who used the activation code"),
        on_delete=models.CASCADE,
        related_name="activation",
    )

    activation_code = models.ForeignKey(
        ActivationCode,
        verbose_name=_("activation code"),
        help_text=_("The activation code that was used"),
        on_delete=models.PROTECT,
        related_name="usages",
    )

    class Meta:
        db_table = "user_activation"
        verbose_name = _("user activation")
        verbose_name_plural = _("user activations")
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the user activation."""
        return f"{self.user} - {self.activation_code.code}"


class UserRegistrationRequest(BaseModel):
    """
    Records of user registration requests.
    """

    user = models.OneToOneField(
        User,
        verbose_name=_("user"),
        help_text=_("The user who made the registration request"),
        on_delete=models.CASCADE,
        related_name="registration_request",
    )

    user_activation = models.OneToOneField(
        UserActivation,
        verbose_name=_("user activation"),
        help_text=_("Store if the user received an activation code and used it"),
        on_delete=models.SET_NULL,
        related_name="registration_request",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "user_registration_request"
        verbose_name = _("user registration request")
        verbose_name_plural = _("user registration requests")
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the user registration request."""
        return f"Registration request by {self.user}"
