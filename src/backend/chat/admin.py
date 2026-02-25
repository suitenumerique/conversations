"""Admin classes and registrations for chat application."""

from django.contrib import admin

from . import models


@admin.register(models.ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversation model"""

    autocomplete_fields = ("owner", "project")
    list_select_related = ("project",)

    list_display = (
        "id",
        "title",
        "project",
        "created_at",
        "updated_at",
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
