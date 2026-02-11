"""Authentication Backends for the Conversations core app."""

import logging

from django.conf import settings
from django.core.exceptions import SuspiciousOperation

from lasuite.oidc_login.backends import (
    OIDCAuthenticationBackend as LaSuiteOIDCAuthenticationBackend,
)

from core.brevo import add_user_to_brevo_list
from core.models import DuplicateEmailError

logger = logging.getLogger(__name__)


class OIDCAuthenticationBackend(LaSuiteOIDCAuthenticationBackend):
    """Custom OpenID Connect (OIDC) Authentication Backend.

    This class overrides the default OIDC Authentication Backend to accommodate differences
    in the User and Identity models, and handles signed and/or encrypted UserInfo response.
    """

    def get_extra_claims(self, user_info):
        """
        Return extra claims from user_info.

        Args:
          user_info (dict): The user information dictionary.

        Returns:
          dict: A dictionary of extra claims.
        """
        return {
            "full_name": self.compute_full_name(user_info),
            "short_name": user_info.get(settings.OIDC_USERINFO_SHORTNAME_FIELD),
        }

    def get_existing_user(self, sub, email):
        """Fetch existing user by sub or email."""

        try:
            return self.UserModel.objects.get_user_by_sub_or_email(sub, email)
        except DuplicateEmailError as err:
            raise SuspiciousOperation(err.message) from err

    def create_user(self, claims):
        """
        Create a new user with the given claims.

        This is the only place where we create users, so we set the default value
        for allow_conversation_analytics here.
        This allows to enable analytics by default during the alpha version and get
        more information about the usage of the application.
        """
        return super().create_user(
            claims
            | {
                "allow_conversation_analytics": settings.DEFAULT_ALLOW_CONVERSATION_ANALYTICS,
                "allow_smart_web_search": settings.DEFAULT_ALLOW_SMART_WEB_SEARCH,
            }
        )

    def authenticate(self, request, **kwargs):
        """Authenticate user and add they to Brevo list if activation not required."""
        user = super().authenticate(request, **kwargs)

        if user and not settings.ACTIVATION_REQUIRED and settings.BREVO_FOLLOWUP_LIST_ID:
            add_user_to_brevo_list([user.email], settings.BREVO_FOLLOWUP_LIST_ID)

        return user
