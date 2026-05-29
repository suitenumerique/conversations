"""Admin classes and registrations for chat application."""

from django.contrib import admin
from django.db.models import OuterRef, Subquery

from . import models


@admin.register(models.ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversation model"""

    search_fields = ("id", "title", "owner__email", "owner__sub")
    ordering = ("-updated_at",)

    autocomplete_fields = ("owner", "project")
    list_select_related = ("project",)

    list_display = (
        "id",
        "title",
        "project",
        "created_at",
        "updated_at",
    )


@admin.register(models.ChatConversationAttachment)
class ChatConversationAttachmentAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversationAttachment model"""

    search_fields = (
        "conversation__id",
        "project__id",
        "file_name",
    )
    ordering = ("-created_at",)
    list_per_page = 50
    show_full_result_count = False
    readonly_fields = ("content_type", "upload_state", "size")
    list_display = (
        "id",
        "file_name",
        "content_type",
        "upload_state",
        "size",
        "conversation",
        "project",
        "uploaded_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("conversation", "project", "uploaded_by")
    list_filter = ("content_type",)
    list_select_related = (
        "conversation",
        "project",
        "uploaded_by",
    )


@admin.register(models.ModelHealth)
class ModelHealthAdmin(admin.ModelAdmin):
    """Read-only admin showing the latest health status per (provider, model)."""

    list_display = ("provider", "model_id", "status", "created_at", "updated_at")
    list_filter = ("provider", "status")

    def get_queryset(self, request):
        latest_id = (
            models.ModelHealth.objects.filter(
                provider=OuterRef("provider"), model_id=OuterRef("model_id")
            )
            .order_by("-updated_at")
            .values("id")[:1]
        )
        return super().get_queryset(request).filter(id=Subquery(latest_id))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.ChatProject)
class ChatProjectAdmin(admin.ModelAdmin):
    """Admin class for the ChatProject model"""

    search_fields = ("id", "title")
    ordering = ("-updated_at",)
    list_filter = ("color", "icon")
    autocomplete_fields = ("owner",)
    list_select_related = ("owner",)
    list_display = (
        "id",
        "title",
        "owner",
        "icon",
        "color",
        "created_at",
        "updated_at",
    )
