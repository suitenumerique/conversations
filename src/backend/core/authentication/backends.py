"""Authentication Backends for the Conversations core app."""

import re

from django.conf import settings
from django.core.exceptions import SuspiciousOperation

import structlog
from lasuite.oidc_login.backends import (
    OIDCAuthenticationBackend as LaSuiteOIDCAuthenticationBackend,
)

from core.brevo import add_user_to_brevo_list
from core.models import AccessBypassEmail, DuplicateEmailError, normalize_email

logger = structlog.get_logger(__name__)


# NB: deliberately NOT a SuspiciousOperation/PermissionDenied subclass. Both
# mozilla-django-oidc (authenticate() catches SuspiciousOperation) and Django's
# auth.authenticate() (catches PermissionDenied) would swallow those into a
# `None` result, which redirects to the generic failure URL with no message.
# A plain exception propagates up to OIDCAuthenticationCallbackView, which turns
# it into a redirect to the access-denied page.
class OIDCRoleAccessDenied(Exception):
    """Raised when an authenticated user fails the access policy (role or email domain)."""


def is_email_domain_allowed(email, allowed_domains):
    """Return True if the domain of ``email`` matches one of ``allowed_domains``.

    An entry ``example.org`` matches that exact domain; an entry ``*.example.org``
    matches any subdomain of it (``a.example.org``, ``a.b.example.org``) but not
    ``example.org`` itself. Matching ignores ASCII case.
    """
    normalized_email = normalize_email(email)
    if not normalized_email or "@" not in normalized_email:
        return False
    domain = normalized_email.rsplit("@", 1)[1]
    if not domain:
        return False

    for raw_entry in allowed_domains:
        entry = normalize_email(raw_entry)
        if not entry:
            continue
        if entry.startswith("*."):
            if domain.endswith(entry[1:]):
                return True
        elif domain == entry:
            return True
    return False


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
        # Only store a well-formed SIRET (14 digits); fall back to an empty
        # string for anything else so a malformed claim never blocks login
        # (the field is optional and non-nullable).
        siret = (user_info.get("siret") or "").strip()
        return {
            "full_name": self.compute_full_name(user_info),
            "short_name": user_info.get(settings.OIDC_USERINFO_SHORTNAME_FIELD),
            "organization_siret": siret if re.fullmatch(r"\d{14}", siret) else "",
        }

    def verify_claims(self, claims):
        """Allow authentication only for users satisfying the access policy.

        Extends the base essential-claim verification with two optional gates,
        each disabled when its setting is empty (default behavior):

        - ``OIDC_ALLOWED_ROLES``: the user must expose at least one of those
          roles in the claim named by ``OIDC_ROLES_CLAIM`` (``roles`` by
          default; a flat list, the shape used by Keycloak in dev, ProConnect in
          production and Mon compte under ``proconnect:roles``).
        - ``OIDC_ALLOWED_EMAIL_DOMAINS``: the domain of the ``email`` claim must
          match one of those entries (see :func:`is_email_domain_allowed`).

        When both are configured, both must be satisfied. This gates both login
        and account creation, since it runs before either branch in
        ``get_or_create_user``.

        As a fallback, a user failing the policy is still allowed in if their
        email is on the :class:`~core.models.AccessBypassEmail` allow-list
        (active and not expired).
        """
        if not super().verify_claims(claims):
            return False

        allowed_roles = settings.OIDC_ALLOWED_ROLES
        allowed_domains = settings.OIDC_ALLOWED_EMAIL_DOMAINS
        if not allowed_roles and not allowed_domains:
            return True

        email = claims.get("email")
        user_roles = claims.get(settings.OIDC_ROLES_CLAIM) or []
        if isinstance(user_roles, str):
            user_roles = user_roles.split()

        role_ok = not allowed_roles or bool(set(allowed_roles) & set(user_roles))
        domain_ok = not allowed_domains or is_email_domain_allowed(email, allowed_domains)
        if role_ok and domain_ok:
            return True

        # Fallback: allow users explicitly added to the access bypass list,
        # even though they fail the policy.
        if AccessBypassEmail.is_email_allowed(email):
            return True

        if not role_ok:
            logger.warning(
                "oidc_access_denied_missing_role",
                sub=claims.get("sub"),
                roles=user_roles,
                allowed_roles=allowed_roles,
            )
        if not domain_ok:
            logger.warning(
                "oidc_access_denied_email_domain",
                sub=claims.get("sub"),
                email_domain=(normalize_email(email) or "").rpartition("@")[2],
                allowed_domains=allowed_domains,
            )
        raise OIDCRoleAccessDenied("User does not satisfy the application access policy.")

    def get_existing_user(self, sub, email):
        """Fetch existing user by sub or email."""

        try:
            return self.UserModel.objects.get_user_by_sub_or_email(sub, email)
        except DuplicateEmailError as err:
            raise SuspiciousOperation(err.message) from err

    def update_user_if_needed(self, user, claims):
        """Compare the email claim in its stored form.

        Stored emails are normalized, so an identity provider sending another ASCII
        case would otherwise rewrite the email on every login.
        """
        if claims.get("email"):
            claims = claims | {"email": normalize_email(claims["email"])}
        super().update_user_if_needed(user, claims)

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

    def post_get_or_create_user(self, user, claims, is_new_user):
        """Add the user to the Brevo follow-up list.

        Only on signup: adding a contact already in the list is a no-op for Brevo, so
        doing it on every login only costs an HTTP round-trip in the login path.

        A failure is logged and never retried (as in every other Brevo call site).
        The follow-up list is a marketing aid: recovering a missed contact is a
        re-import, not something worth persisting per-user state for.
        """
        if is_new_user and settings.BREVO_FOLLOWUP_LIST_ID:
            add_user_to_brevo_list([user.email], settings.BREVO_FOLLOWUP_LIST_ID)
