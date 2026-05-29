"""Admin classes and registrations for core app."""

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from solo.admin import SingletonModelAdmin

from . import models


@admin.register(models.User)
class UserAdmin(auth_admin.UserAdmin):
    """Admin class for the User model"""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "admin_email",
                    "password",
                )
            },
        ),
        (
            _("Personal info"),
            {
                "fields": (
                    "sub",
                    "email",
                    "full_name",
                    "short_name",
                    "language",
                    "timezone",
                    "allow_smart_web_search",
                    "allow_conversation_analytics",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_device",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    list_display = (
        "id",
        "sub",
        "full_name",
        "admin_email",
        "email",
        "is_active",
        "allow_smart_web_search",
        "allow_conversation_analytics",
        "is_staff",
        "is_superuser",
        "is_device",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_device",
        "is_active",
        "allow_smart_web_search",
        "allow_conversation_analytics",
    )
    ordering = (
        "is_active",
        "-is_superuser",
        "-is_staff",
        "-is_device",
        "-updated_at",
        "full_name",
    )
    readonly_fields = (
        "id",
        "sub",
        "email",
        "full_name",
        "short_name",
        "created_at",
        "updated_at",
        "allow_smart_web_search",
        "allow_conversation_analytics",
    )
    search_fields = (
        "id",
        "sub",
        "admin_email",
        "email",
        "full_name",
    )


@admin.register(models.ModelHealthSettings)
class ModelHealthSettingsAdmin(SingletonModelAdmin):
    """Admin for the ModelHealthSettings singleton."""


@admin.register(models.SiteConfiguration)
class SiteConfigurationAdmin(SingletonModelAdmin):
    """Admin class for the SiteConfiguration model"""

    fieldsets = (
        (
            _("Self documentation"),
            {
                "description": _(
                    "Markdown documentation about this service. Exposed to "
                    "the conversation agent so it can answer questions "
                    "users ask about the app itself."
                ),
                "fields": ("self_documentation",),
            },
        ),
        (
            _("Status banner"),
            {
                "description": _(
                    "Shown to all users at the top of the app. "
                    "Leave title and content empty to disable."
                ),
                "fields": (
                    "status_banner_level",
                    "status_banner_title",
                    "status_banner_content",
                    "status_banner_starts_at",
                    "status_banner_ends_at",
                ),
            },
        ),
    )


@admin.register(models.MaintenanceMode)
class MaintenanceModeAdmin(SingletonModelAdmin):
    """Admin class for the MaintenanceMode singleton."""

    fields = ("enabled", "message", "starts_at", "ends_at", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if settings.MAINTENANCE_MODE:
            messages.warning(
                request,
                _(
                    "The MAINTENANCE_MODE environment variable is set: maintenance is "
                    "forced ON regardless of the value below."
                ),
            )
        return super().changeform_view(request, object_id, form_url, extra_context)
