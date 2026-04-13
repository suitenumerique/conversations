"""Admin classes and registrations for chat application."""

from django.contrib import admin

from . import models


@admin.register(models.ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversation model"""

    search_fields = ("id",)

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
class AttachmentAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversationAttachment model"""

    search_fields = (
        "conversation__id",
        "project__id",
    )
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
    # autocomplete_fields = ("conversation", "uploaded_by")
    list_filter = ("content_type",)
    list_select_related = (
        "conversation",
        "project",
        "uploaded_by",
    )


@admin.register(models.ChatProject)
class ChatProjectAdmin(admin.ModelAdmin):
    """Admin class for the ChatProject model"""

    search_fields = ("title",)
    list_display = (
        "id",
        "title",
        "icon",
        "color",
        "created_at",
        "updated_at",
    )
