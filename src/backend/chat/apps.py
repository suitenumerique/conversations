"""Chat application"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChatDefaultConfig(AppConfig):
    """Configuration class for the chat application."""

    name = "chat"
    app_label = "chat"
    verbose_name = _("chat application")

    def ready(self):
        """Register the chat system checks (chat.E101)."""
        # pylint: disable-next=import-outside-toplevel,unused-import
        from chat import checks  # noqa: PLC0415
