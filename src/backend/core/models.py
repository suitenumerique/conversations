"""
Declare and configure the models for the conversations core application
"""

import uuid
from logging import getLogger

from django.conf import settings
from django.contrib.auth import models as auth_models
from django.contrib.auth.base_user import AbstractBaseUser
from django.core import mail, validators
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from solo.models import SingletonModel
from timezone_field import TimeZoneField

logger = getLogger(__name__)


class DuplicateEmailError(Exception):
    """Raised when an email is already associated with a pre-existing user."""

    def __init__(self, message=None, email=None):
        """Set message and email to describe the exception."""
        self.message = message
        self.email = email
        super().__init__(self.message)


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


class UserManager(auth_models.UserManager):
    """Custom manager for User model with additional methods."""

    def get_user_by_sub_or_email(self, sub, email):
        """Fetch existing user by sub or email."""
        try:
            return self.get(sub=sub)
        except self.model.DoesNotExist as err:
            if not email:
                return None

            if settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION:
                try:
                    return self.get(email__iexact=email)
                except self.model.DoesNotExist:
                    pass
            elif (
                self.filter(email__iexact=email).exists()
                and not settings.OIDC_ALLOW_DUPLICATE_EMAILS
            ):
                raise DuplicateEmailError(
                    _(
                        "We couldn't find a user with this sub but the email is already "
                        "associated with a registered user."
                    )
                ) from err
        return None


class User(AbstractBaseUser, BaseModel, auth_models.PermissionsMixin):
    """User model to work with OIDC only authentication."""

    sub_validator = validators.RegexValidator(
        regex=r"^[\w.@+-:]+\Z",
        message=_(
            "Enter a valid sub. This value may contain only letters, "
            "numbers, and @/./+/-/_/: characters."
        ),
    )

    sub = models.CharField(
        _("sub"),
        help_text=_(
            "Required. 255 characters or fewer. Letters, numbers, and @/./+/-/_/: characters only."
        ),
        max_length=255,
        unique=True,
        validators=[sub_validator],
        blank=True,
        null=True,
    )

    full_name = models.CharField(_("full name"), max_length=100, null=True, blank=True)
    short_name = models.CharField(_("short name"), max_length=50, null=True, blank=True)

    email = models.EmailField(_("identity email address"), blank=True, null=True)

    # Unlike the "email" field which stores the email coming from the OIDC token, this field
    # stores the email used by staff users to login to the admin site
    admin_email = models.EmailField(_("admin email address"), unique=True, blank=True, null=True)

    language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default=None,
        verbose_name=_("language"),
        help_text=_("The language in which the user wants to see the interface."),
        null=True,
        blank=True,
    )
    timezone = TimeZoneField(
        choices_display="WITH_GMT_OFFSET",
        use_pytz=False,
        default=settings.TIME_ZONE,
        help_text=_("The timezone in which the user wants to see times."),
    )
    is_device = models.BooleanField(
        _("device"),
        default=False,
        help_text=_("Whether the user is a device or a real user."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    # Application specific fields
    allow_conversation_analytics = models.BooleanField(
        _("allow conversation analytics"),
        default=False,
        help_text=_("Whether the user allows to use their conversations for analytics."),
    )

    allow_smart_web_search = models.BooleanField(
        _("allow smart web search"),
        default=False,
        help_text=_("Whether the user allows to use smart web search features."),
    )

    # Organization SIRET from the OIDC "siret" claim, refreshed on every login.
    # Empty string (not NULL) when absent or malformed, per Django's convention
    # for optional string fields.
    organization_siret = models.CharField(
        _("organization SIRET"),
        max_length=14,
        blank=True,
        db_index=True,
        help_text=_("SIRET of the user's organization, as provided by the identity provider."),
    )

    objects = UserManager()

    USERNAME_FIELD = "admin_email"
    REQUIRED_FIELDS = []

    class Meta:  # pylint:disable=missing-class-docstring
        db_table = "conversations_user"
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        """Return a string representation of the user."""
        return self.email or self.admin_email or str(self.id)

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Email this user."""
        if not self.email:
            raise ValueError("User has no email address.")
        mail.send_mail(subject, message, from_email, [self.email], **kwargs)


class BannerLevelChoice(models.TextChoices):
    """Banner level info"""

    INFO = "info", _("Info")
    WARNING = "warning", _("Warning")
    ALERT = "alert", _("Alert")


class SiteConfiguration(SingletonModel):
    """Singleton model for site configuration"""

    self_documentation = models.TextField(
        verbose_name=_("Self documentation content. Must be valid markdown."),
        blank=True,
        default="",
    )

    # Status/incident banner
    status_banner_level = models.CharField(
        verbose_name=_("Status banner - level"),
        max_length=20,
        choices=BannerLevelChoice.choices,
        default=BannerLevelChoice.INFO,
    )
    status_banner_title = models.CharField(
        blank=True,
        verbose_name=_("Status banner - title"),
    )
    status_banner_content = models.TextField(
        blank=True,
        verbose_name=_("Status banner - content"),
    )
    status_banner_starts_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Status banner - starts at"),
        help_text=_("If set, the banner is hidden before this date."),
    )
    status_banner_ends_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Status banner - ends at"),
        help_text=_("If set, the banner is hidden after this date."),
    )

    @property
    def status_banner_visible(self):
        """Is the banner visible?"""
        if not self.status_banner_title:
            return False
        now = timezone.now()
        if self.status_banner_starts_at and now < self.status_banner_starts_at:
            return False
        if self.status_banner_ends_at and now > self.status_banner_ends_at:
            return False
        return True

    class Meta:
        verbose_name = _("Site Configuration")


class MaintenanceMode(SingletonModel):
    """Singleton holding the live maintenance-mode state.

    When active, non-exempt requests are short-circuited with HTTP 503 by
    `MaintenanceMiddleware`. Always OR'd with `settings.MAINTENANCE_MODE`
    (env-var escape hatch).
    """

    enabled = models.BooleanField(
        default=False,
        verbose_name=_("Enabled"),
        help_text=_("When checked, the app is in maintenance mode for end-users."),
    )
    message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Message"),
        help_text=_("Shown on the maintenance page. Leave blank for the default message."),
    )
    starts_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Starts at"),
        help_text=_("If set, maintenance is inactive before this date."),
    )
    ends_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Ends at"),
        help_text=_("If set, maintenance is inactive after this date."),
    )
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        editable=False,
        related_name="+",
    )

    def is_active_now(self) -> bool:
        """Whether the DB-driven maintenance window is currently active."""
        if not self.enabled:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    def save(self, *args, **kwargs):
        if self.pk:
            previous = (
                type(self).objects.filter(pk=self.pk).values_list("enabled", flat=True).first()
            )
        else:
            previous = None
        super().save(*args, **kwargs)
        if previous is not None and previous != self.enabled:
            logger.warning(
                "maintenance mode %s (singleton)",
                "ENABLED" if self.enabled else "DISABLED",
            )

    class Meta:
        verbose_name = _("Maintenance Mode")


class ModelHealthSettings(SingletonModel):
    """Singleton controlling the model-health polling behaviour."""

    poll_interval_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Minimum minutes between two effective polling runs.",
    )

    class Meta:  # pylint: disable=missing-class-docstring
        verbose_name = "Model Health Settings"


class AccessBypassEmail(BaseModel):
    """Allow-list of email addresses that may sign in even without the role
    normally required by the OIDC access policy (see ``OIDC_ALLOWED_ROLES``).

    Used as a fallback in the authentication backend: a user who lacks the
    required role is still granted access if their email matches an active,
    non-expired entry here.
    """

    email = models.EmailField(
        _("email address"),
        unique=True,
        help_text=_("email address allowed to bypass the role requirement"),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("inactive entries are ignored without being deleted"),
    )
    note = models.TextField(
        _("note"),
        blank=True,
        help_text=_("optional reason for granting this bypass"),
    )
    expires_at = models.DateTimeField(
        _("expires on"),
        blank=True,
        null=True,
        help_text=_("optional date after which this bypass no longer applies"),
    )

    class Meta:
        db_table = "conversations_access_bypass_email"
        verbose_name = _("access bypass email")
        verbose_name_plural = _("access bypass emails")
        ordering = ("-created_at",)

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        """Store the email normalized (trimmed, lowercase) for case-insensitive matching."""
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @classmethod
    def is_email_allowed(cls, email):
        """Return True if ``email`` has an active, non-expired bypass entry."""
        if not email:
            return False
        return (
            cls.objects.filter(email__iexact=email.strip(), is_active=True)
            .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))
            .exists()
        )
