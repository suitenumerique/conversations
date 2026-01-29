"""Admin classes and registrations for core app."""

from django.contrib import admin
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
    )
    search_fields = (
        "id",
        "sub",
        "admin_email",
        "email",
        "full_name",
        "allow_conversation_analytics",
    )
    list_editable = ("allow_conversation_analytics",)


@admin.register(models.SiteConfiguration)
class SiteConfigurationAdmin(SingletonModelAdmin):
  fieldsets = (
      (_("Environment Banner"), {
          "description": _("Inform users about the current environment (staging, demo...)"),
          "fields": (
              "environment_banner_level",
              "environment_banner_title",
              "environment_banner_content",
          ),
      }),
      (_("Status / Incident Banner"), {
          "description": _("Communicate maintenance windows or ongoing incidents"),
          "fields": (
              "status_banner_level",
              "status_banner_title",
                   "status_banner_content",
              "status_banner_dismissible",
          ),
      }),
  )
