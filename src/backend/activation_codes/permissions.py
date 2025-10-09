"""Permission classes for activation codes."""

from django.conf import settings

from rest_framework import permissions

from . import models


class IsActivatedUser(permissions.BasePermission):
    """
    Permission class that checks if user has activated their account.

    This permission is only enforced if ACTIVATION_REQUIRED is True in settings.
    Staff users and users without authentication requirement are always allowed.
    """

    message = "activation-required"  # Custom message to indicate activation is required to frontend

    def has_permission(self, request, view):
        """Check if user has activated their account."""
        # If activation is not required, allow access
        if not settings.ACTIVATION_REQUIRED:
            return True

        # Staff users can always access
        if request.user and request.user.is_staff:
            return True

        # Anonymous users are handled by other permission classes
        if not request.user or not request.user.is_authenticated:
            return True

        # Check if user has an activation record
        return models.UserActivation.objects.filter(user=request.user).exists()

    def has_object_permission(self, request, view, obj):
        """Check object-level permission."""
        return self.has_permission(request, view)
