"""Admin classes and registrations for chat application."""

from django.contrib import admin

from . import models


@admin.register(models.ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversation model"""

    search_fields = ("id", "title", "owner__email", "owner__sub", "project__title")
    ordering = ("-updated_at",)
    date_hierarchy = "created_at"

    autocomplete_fields = ("owner", "project")
    list_select_related = ("owner", "project")
    list_filter = (
        ("project", admin.EmptyFieldListFilter),
        ("collection_id", admin.EmptyFieldListFilter),
    )

    list_display = (
        "id",
        "title",
        "owner",
        "project",
        "collection_id",
        "created_at",
        "updated_at",
    )


@admin.register(models.ChatConversationAttachment)
class ChatConversationAttachmentAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversationAttachment model"""

    search_fields = (
        "id",
        "conversation__id",
        "project__id",
        "file_name",
        "key",
        "rag_document_id",
        "uploaded_by__email",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    show_full_result_count = False
    readonly_fields = ("content_type", "upload_state", "size")
    list_display = (
        "id",
        "file_name",
        "scope",
        "content_type",
        "upload_state",
        "size",
        "conversation",
        "project",
        "uploaded_by",
        "rag_document_id",
        "conversion_from",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("conversation", "project", "uploaded_by")
    list_filter = (
        "content_type",
        ("rag_document_id", admin.EmptyFieldListFilter),
        ("conversion_from", admin.EmptyFieldListFilter),
    )
    list_select_related = (
        "conversation",
        "project",
        "uploaded_by",
    )

    @admin.display(description="Scope")
    def scope(self, obj):
        """Show whether the attachment is owned by a conversation or a project."""
        if obj.conversation_id:
            return "conversation"
        if obj.project_id:
            return "project"
        return "-"


@admin.register(models.ChatProject)
class ChatProjectAdmin(admin.ModelAdmin):
    """Admin class for the ChatProject model"""

    search_fields = ("id", "title")
    ordering = ("-updated_at",)
    date_hierarchy = "created_at"
    list_filter = ("color", "icon")
    autocomplete_fields = ("owner",)
    list_select_related = ("owner",)
    list_display = (
        "id",
        "title",
        "owner",
        "collection_id",
        "icon",
        "color",
        "created_at",
        "updated_at",
    )
