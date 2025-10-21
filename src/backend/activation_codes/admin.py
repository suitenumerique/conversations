"""Admin classes for activation codes application."""

from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from . import models


@admin.register(models.ActivationCode)
class ActivationCodeAdmin(admin.ModelAdmin):
    """Admin class for ActivationCode model"""

    list_display = (
        "code",
        "usage_display",
        "is_active",
        "expires_at",
        "created_at",
        "description_short",
    )

    list_filter = (
        "is_active",
        "created_at",
        "expires_at",
    )

    search_fields = (
        "code",
        "description",
    )

    readonly_fields = (
        "id",
        "current_uses",
        "created_at",
        "updated_at",
        "usage_details",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "code",
                    "description",
                )
            },
        ),
        (
            _("Configuration"),
            {
                "fields": (
                    "max_uses",
                    "current_uses",
                    "is_active",
                    "expires_at",
                )
            },
        ),
        (
            _("Usage details"),
            {"fields": ("usage_details",)},
        ),
        (
            _("Timestamps"),
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    actions = ["recompute_current_uses"]

    def get_readonly_fields(self, request, obj=None):
        """Make `code` readonly when editing an existing ActivationCode.

        When obj is None (creation form), `code` remains editable. When obj is
        provided (editing), add `code` to readonly fields so it cannot be
        changed after creation.
        """
        # Start from the configured readonly_fields to preserve other read-only fields
        ro_fields = list(self.readonly_fields)
        if obj is not None:
            ro_fields.append("code")
        return tuple(ro_fields)

    def usage_display(self, obj):
        """Display usage statistics."""
        max_uses = obj.max_uses if obj.max_uses > 0 else "∞"
        if obj.current_uses >= obj.max_uses and obj.max_uses > 0:
            color = "red"
        elif obj.current_uses > 0:
            color = "orange"
        else:
            color = "green"

        return format_html(
            '<span style="color: {};">{} / {}</span>', color, obj.current_uses, max_uses
        )

    usage_display.short_description = _("Usage")

    def description_short(self, obj):
        """Display truncated description."""
        if obj.description:
            return obj.description[:50] + "..." if len(obj.description) > 50 else obj.description
        return "-"

    description_short.short_description = _("Description")

    def usage_details(self, obj):
        """Display detailed usage information."""
        usages = obj.usages.select_related("user").all()

        if not usages:
            return _("No users have used this code yet")

        table_head = format_html(
            (
                "<table style='width: 100%; border-collapse: collapse;'>"
                "<tr style='background-color: #f0f0f0;'>"
                "<th style='padding: 8px; text-align: left;'>{name}</th>"
                "<th style='padding: 8px; text-align: left;'>{title}</th>"
                "<th style='padding: 8px; text-align: left;'>{date}</th>"
                "</tr>"
            ),
            name=_("Name"),
            title=_("Email"),
            date=_("Date"),
        )

        rows = format_html_join(
            "",
            (
                "<tr style='border-bottom: 1px solid #ddd;'>"
                "<td style='padding: 8px;'>{name}</td>"
                "<td style='padding: 8px;'>{email}</td>"
                "<td style='padding: 8px;'>{created_at}</td>"
                "</tr>"
            ),
            (
                {
                    "name": usage.user.full_name or "-",
                    "email": usage.user.email or "-",
                    "created_at": usage.created_at.strftime("%Y-%m-%d %H:%M"),
                }
                for usage in usages
            ),
        )

        return format_html("{table_head}{rows}</table>", table_head=table_head, rows=rows)

    usage_details.short_description = _("Users who used this code")

    @admin.action(description=_("Recompute current uses from related activations"))
    def recompute_current_uses(self, request, queryset):
        """Recompute the current_uses field by counting related UserActivation objects."""
        updated_count = 0
        for activation_code in queryset:
            actual_uses = activation_code.usages.count()
            if activation_code.current_uses != actual_uses:
                activation_code.current_uses = actual_uses
                activation_code.save(update_fields=["current_uses", "updated_at"])
                updated_count += 1

        if updated_count == 0:
            self.message_user(
                request,
                _("All selected activation codes already have correct usage counts."),
            )
        else:
            self.message_user(
                request,
                _("Successfully recomputed usage counts for %(count)d activation code(s).")
                % {"count": updated_count},
            )


@admin.register(models.UserActivation)
class UserActivationAdmin(admin.ModelAdmin):
    """Admin class for UserActivation model"""

    list_display = (
        "user_display",
        "user_email",
        "activation_code",
        "created_at",
    )

    list_filter = ("created_at",)

    search_fields = (
        "user__email",
        "user__full_name",
        "activation_code__code",
    )

    readonly_fields = (
        "id",
        "user",
        "activation_code",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "user",
                    "activation_code",
                )
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def user_display(self, obj):
        """Display user's full name."""
        return obj.user.full_name or str(obj.user.id)

    user_display.short_description = _("User")

    def user_email(self, obj):
        """Display user's email."""
        return obj.user.email or "-"

    user_email.short_description = _("Email")

    def has_add_permission(self, request):
        """Disable manual creation of user activations."""
        return False


@admin.register(models.UserRegistrationRequest)
class UserRegistrationRequestAdmin(admin.ModelAdmin):
    """Admin class for UserRegistrationRequest model"""

    list_display = (
        "user_display",
        "created_at",
        "has_user_activation",
    )

    readonly_fields = (
        "id",
        "user",
        "created_at",
        "updated_at",
        "user_activation",
    )

    search_fields = (
        "user__email",
        "user__full_name",
    )

    list_filter = ("created_at",)

    actions = ["add_to_brevo_waiting_list", "remove_from_brevo_waiting_list"]

    def user_display(self, obj):
        """Display user's full name."""
        return obj.user.email or str(obj.user.pk)

    user_display.short_description = _("User")

    def has_user_activation(self, obj):
        """Indicate if the user has used an activation code."""
        return obj.user_activation_id is not None

    has_user_activation.boolean = True
    has_user_activation.short_description = _("Has used activation code")

    @admin.action(description=_("Add selected users to Brevo waiting list"))
    def add_to_brevo_waiting_list(self, request, queryset):
        """Add selected users to Brevo waiting list."""
        # pylint: disable=import-outside-toplevel
        from core.brevo import add_user_to_brevo_list  # noqa: PLC0415

        registration_to_send = queryset.filter(
            user_activation__isnull=True,
        )

        _total_emails = 0
        for i in range(0, registration_to_send.count(), 150):
            batch = registration_to_send[i : i + 150]
            emails = [reg.user.email for reg in batch if reg.user.email]
            if emails:
                add_user_to_brevo_list(emails, settings.BREVO_WAITING_LIST_ID)
                _total_emails += len(emails)

        if _total_emails:
            self.message_user(
                request,
                _("Added %(count)d user(s) to Brevo waiting list.") % {"count": _total_emails},
            )
        else:
            self.message_user(
                request,
                _("No valid email address found in selected registrations."),
                level="warning",
            )

    @admin.action(description=_("Remove selected users from Brevo waiting list"))
    def remove_from_brevo_waiting_list(self, request, queryset):
        """Remove selected users from Brevo waiting list."""
        # pylint: disable=import-outside-toplevel
        from core.brevo import remove_user_from_brevo_list  # noqa: PLC0415

        registration_to_send = queryset.filter(
            user_activation__isnull=False,
        )
        _total_emails = 0
        for i in range(0, registration_to_send.count(), 150):
            batch = registration_to_send[i : i + 150]
            emails = [reg.user.email for reg in batch if reg.user.email]
            if emails:
                remove_user_from_brevo_list(emails, settings.BREVO_WAITING_LIST_ID)
                _total_emails += len(emails)
        if _total_emails:
            self.message_user(
                request,
                _("Removed %(count)d user(s) from Brevo waiting list.") % {"count": _total_emails},
            )
        else:
            self.message_user(
                request,
                _("No valid email address found in selected registrations."),
                level="warning",
            )
