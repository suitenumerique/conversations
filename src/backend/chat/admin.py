"""Admin classes and registrations for chat application."""

from django.contrib import admin

from . import models


@admin.register(models.ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    """Admin class for the ChatConversation model"""

    autocomplete_fields = ("owner",)

    list_display = (
        "id",
        "title",
        "created_at",
        "updated_at",
    )
