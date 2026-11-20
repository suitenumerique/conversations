"""Chat application"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChatDefaultConfig(AppConfig):
    """Configuration class for the chat application."""

    name = "chat"
    app_label = "chat"
    verbose_name = _("chat application")

    def ready(self):
        """Register the connector declarations check."""
        # pylint: disable=import-outside-toplevel,unused-import
        from chat.connectors import registry  # noqa: PLC0415
