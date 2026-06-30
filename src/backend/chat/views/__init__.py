"""Chat API views.

The implementation is split across submodules; this package re-exports the
public view classes so ``core.urls`` and existing imports keep working.
"""

from chat.views.attachments import (
    BaseAttachmentViewSet,
    ChatConversationAttachmentViewSet,
    ChatProjectAttachmentViewSet,
)
from chat.views.conversations import ChatAttachmentMixin, ChatCooldownView, ChatViewSet
from chat.views.files import FileStreamView
from chat.views.filters import ProjectFilter, TitleSearchFilter
from chat.views.health import AssistantHealthView, ModelHealthView
from chat.views.llm_config import LLMConfigurationView
from chat.views.projects import ChatProjectViewSet

__all__ = [
    "AssistantHealthView",
    "BaseAttachmentViewSet",
    "ChatAttachmentMixin",
    "ChatConversationAttachmentViewSet",
    "ChatCooldownView",
    "ChatProjectAttachmentViewSet",
    "ChatProjectViewSet",
    "ChatViewSet",
    "FileStreamView",
    "LLMConfigurationView",
    "ModelHealthView",
    "ProjectFilter",
    "TitleSearchFilter",
]
