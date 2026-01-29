from django.db import models
from django.utils.translation import gettext_lazy as _
from solo.models import SingletonModel


class BannerLevelChoice(models.TextChoices):
    INFO = "info", _("Info")
    WARNING = "warning", _("Warning")
    ALERT = "alert", _("Alert")


class SiteConfiguration(SingletonModel):
    """Site-wide configuration for banners and announcements."""

    # Environment banner (staging, demo, QA, sandbox, etc.)
    environment_banner_title = models.CharField(
        blank=True,
        verbose_name=_("Environment banner - title"),
    )
    environment_banner_content = models.TextField(
        blank=True,
        verbose_name=_("Environment banner - content"),
    )
    environment_banner_level = models.CharField(
        verbose_name=_("Environment banner - level"),
        max_length=20,
        choices=BannerLevelChoice.choices,
        default=BannerLevelChoice.INFO,
    )

    # Status/incident banner
    status_banner_title = models.CharField(
        blank=True,
        verbose_name=_("Status banner - title"),
    )
    status_banner_content = models.TextField(
        blank=True,
        verbose_name=_("Status banner - content"),
    )
    status_banner_level = models.CharField(
        verbose_name=_("Status banner - level"),
        max_length=20,
        choices=BannerLevelChoice.choices,
        default=BannerLevelChoice.INFO,
    )
    status_banner_dismissible = models.BooleanField(
        default=True,
        verbose_name=_("Status banner - dismissible"),
        help_text=_("Allow users to dismiss this banner"),
    )

    def __str__(self):
        return "Site Configuration"

    @property
    def environment_banner_enabled(self):
        return bool(self.environment_banner_title or self.environment_banner_content)

    @property
    def status_banner_enabled(self):
        return bool(self.status_banner_title or self.status_banner_content)

    class Meta:
        verbose_name = _("Site Configuration" )
