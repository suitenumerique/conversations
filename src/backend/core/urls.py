"""URL configuration for the core app."""

from django.conf import settings
from django.urls import include, path

from lasuite.oidc_login.urls import urlpatterns as oidc_urls
from rest_framework.routers import DefaultRouter

from core.api import viewsets

from activation_codes import viewsets as activation_viewsets
from chat.views import (
    ChatConversationAttachmentViewSet,
    ChatViewSet,
    LLMConfigurationView,
    MCPTestConnectionView,
)

# - Main endpoints
router = DefaultRouter()
router.register("users", viewsets.UserViewSet, basename="users")
router.register("chats", ChatViewSet, basename="chats")
router.register("activation", activation_viewsets.ActivationViewSet, basename="activation")

conversation_router = DefaultRouter()
conversation_router.register(
    "attachments", ChatConversationAttachmentViewSet, basename="conversation-attachments"
)

urlpatterns = [
    path(
        f"api/{settings.API_VERSION}/",
        include(
            [
                *router.urls,
                *oidc_urls,
                path(
                    "llm-configuration/", LLMConfigurationView.as_view(), name="llm-configuration"
                ),
                path("mcp-test-connection/", MCPTestConnectionView.as_view(), name="mcp-test-connection"),
                path(
                    "chats/<uuid:conversation_pk>/",
                    include(conversation_router.urls),
                ),
            ]
        ),
    ),
    path(f"api/{settings.API_VERSION}/config/", viewsets.ConfigView.as_view()),
]
