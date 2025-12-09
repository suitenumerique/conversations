"""URL configuration for the core app."""

from django.conf import settings
from django.urls import include, path

from lasuite.oidc_login.urls import urlpatterns as oidc_urls
from rest_framework.routers import DefaultRouter

from core.api import viewsets

from activation_codes import viewsets as activation_viewsets
from chat.views import ChatConversationAttachmentViewSet, ChatViewSet, LLMConfigurationView
from evaluation.views import ChatCompletionsView

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
                path(
                    "chats/<uuid:conversation_pk>/",
                    include(conversation_router.urls),
                ),
            ]
        ),
    ),
    path(f"api/{settings.API_VERSION}/config/", viewsets.ConfigView.as_view()),
]

if settings.ENVIRONMENT in ["development", "tests"]:
    urlpatterns += [
        # Allow access to the OpenAI-like chat completions endpoint only in development and tests
        # on http://localhost:8071/v1/chat/completions
        path("v1/chat/completions", ChatCompletionsView.as_view(), name="chat_completions"),
    ]
