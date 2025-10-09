"""
Models for the activation codes application
"""

import logging
import secrets
import string

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel, User

from activation_codes.exceptions import InvalidCodeError, UserAlreadyActivatedError

logger = logging.getLogger(__name__)


def generate_activation_code():
    """Generate a random 16-character activation code."""
    alphabet = string.ascii_uppercase + string.digits
    # Remove ambiguous characters
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(16))


class ActivationCode(BaseModel):
    """
    Represents an activation code that can be used to activate user accounts.
    """

    code = models.CharField(
        verbose_name=_("activation code"),
        help_text=_("The activation code that users will enter"),
        max_length=50,
        unique=True,
        default=generate_activation_code,
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

    def is_valid(self):
        """Check if the code is still valid and can be used."""
        if not self.is_active:
            return False

        if self.expires_at and self.expires_at < timezone.now():
            return False

        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False

        return True

    def can_be_used(self):
        """Alias for is_valid() for better readability."""
        return self.is_valid()

    def use(self, user):
        """
        Mark this code as used by a user.

        Args:
            user: The User instance using this code

        Returns:
            UserActivation instance

        Raises:
            ValidationError: If the code cannot be used
        """
        with transaction.atomic():
            # Lock the activation code row to prevent concurrent overuse.
            locked_code = ActivationCode.objects.select_for_update().get(pk=self.pk)

            if not locked_code.is_valid():
                raise InvalidCodeError(_("This activation code is no longer valid"))

            # Create activation record; rely on DB uniqueness for concurrent duplicate attempts.
            try:
                activation = UserActivation.objects.create(user=user, activation_code=locked_code)
            except (IntegrityError, ValidationError) as exc:
                # User already has an activation in a concurrent or prior transaction.
                raise UserAlreadyActivatedError(
                    _("You have already activated your account")
                ) from exc

            # Increment usage counter safely under the same lock.
            locked_code.current_uses += 1
            locked_code.save(update_fields=["current_uses", "updated_at"])

            if locked_code.max_uses > 0 and locked_code.current_uses >= locked_code.max_uses:
                logger.warning("Activation code %s has reached its maximum uses", locked_code.code)

            return activation


class UserActivation(BaseModel):
    """
    Records which user used which activation code and when.
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
