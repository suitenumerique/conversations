"""URL configuration for the core app."""

from django.conf import settings
from django.urls import include, path

from lasuite.oidc_login.urls import urlpatterns as oidc_urls
from rest_framework.routers import DefaultRouter

from core.api import viewsets

from chat.views import ChatViewSet

# - Main endpoints
router = DefaultRouter()
router.register("users", viewsets.UserViewSet, basename="users")
router.register("chats", ChatViewSet, basename="chats")

urlpatterns = [
    path(
        f"api/{settings.API_VERSION}/",
        include(
            [
                *router.urls,
                *oidc_urls,
            ]
        ),
    ),
    path(f"api/{settings.API_VERSION}/config/", viewsets.ConfigView.as_view()),
]
