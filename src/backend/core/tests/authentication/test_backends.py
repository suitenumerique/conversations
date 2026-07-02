"""Unit tests for the Authentication Backends."""

import json
import random
import re
from datetime import timedelta

from django.core.exceptions import SuspiciousOperation
from django.test.utils import override_settings
from django.utils import timezone

import pytest
import responses
from cryptography.fernet import Fernet
from lasuite.oidc_login.backends import get_oidc_refresh_token

from core import models
from core.authentication.backends import OIDCAuthenticationBackend, OIDCRoleAccessDenied
from core.factories import AccessBypassEmailFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True, scope="function")
def reset_user_model():
    """Reset the user model before each test to ensure a clean state."""
    models.User.objects.all().delete()


def test_authentication_getter_existing_user_no_email(django_assert_num_queries, monkeypatch):
    """
    If an existing user matches the user's info sub, the user should be returned.
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory()

    def get_userinfo_mocked(*args):
        return {"sub": db_user.sub}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with django_assert_num_queries(1):
        user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user == db_user


def test_authentication_getter_existing_user_via_email(django_assert_num_queries, monkeypatch):
    """
    If an existing user doesn't match the sub but matches the email,
    the user should be returned.
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory()

    def get_userinfo_mocked(*args):
        return {"sub": "123", "email": db_user.email}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with django_assert_num_queries(4):  # user by sub, user by mail, unicity check, update sub
        user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user == db_user


def test_authentication_getter_existing_user_via_email_case_insensitive(
    django_assert_num_queries, monkeypatch
):
    """
    If an existing user doesn't match the sub but matches the email with different case,
    the user should be returned (case-insensitive email matching).
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory(email="john.doe@example.com")

    def get_userinfo_mocked(*args):
        return {"sub": "123", "email": "JOHN.DOE@EXAMPLE.COM"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with django_assert_num_queries(4):  # user by sub, user by mail, update sub
        user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user == db_user


def test_authentication_getter_email_none(monkeypatch):
    """
    If no user is found with the sub and no email is provided, a new user should be created.
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory(email=None)

    def get_userinfo_mocked(*args):
        user_info = {"sub": "123"}
        if random.choice([True, False]):
            user_info["email"] = None
        return user_info

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    # Since the sub and email didn't match, it should create a new user
    assert models.User.objects.count() == 2
    assert user != db_user
    assert user.sub == "123"


def test_authentication_getter_existing_user_no_fallback_to_email_allow_duplicate(
    settings, monkeypatch
):
    """
    When the "OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION" setting is set to False,
    the system should not match users by email, even if the email matches.
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory()

    # Set the setting to False
    settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = False
    settings.OIDC_ALLOW_DUPLICATE_EMAILS = True

    def get_userinfo_mocked(*args):
        return {"sub": "123", "email": db_user.email}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    # Since the sub doesn't match, it should create a new user
    assert models.User.objects.count() == 2
    assert user != db_user
    assert user.sub == "123"


def test_authentication_getter_existing_user_no_fallback_to_email_no_duplicate(
    settings, monkeypatch
):
    """
    When the "OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION" setting is set to False,
    the system should not match users by email, even if the email matches.
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory()

    # Set the setting to False
    settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = False

    def get_userinfo_mocked(*args):
        return {"sub": "123", "email": db_user.email}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with pytest.raises(
        SuspiciousOperation,
        match=(
            "We couldn't find a user with this sub but the email is "
            "already associated with a registered user."
        ),
    ):
        klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    # Since the sub doesn't match, it should not create a new user
    assert models.User.objects.count() == 1


def test_authentication_getter_existing_user_no_fallback_to_email_no_duplicate_case_insensitive(
    settings, monkeypatch
):
    """
    When the "OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION" setting is set to False,
    the system should detect duplicate emails even with different case.
    """

    klass = OIDCAuthenticationBackend()
    _db_user = UserFactory(email="john.doe@example.com")

    # Set the setting to False
    settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = False

    def get_userinfo_mocked(*args):
        return {"sub": "123", "email": "JOHN.DOE@EXAMPLE.COM"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with pytest.raises(
        SuspiciousOperation,
        match=(
            "We couldn't find a user with this sub but the email is already associated "
            "with a registered user."
        ),
    ):
        klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    # Since the sub doesn't match, it should not create a new user
    assert models.User.objects.count() == 1


def test_authentication_getter_existing_user_with_email(django_assert_num_queries, monkeypatch):
    """
    When the user's info contains an email and targets an existing user,
    """
    klass = OIDCAuthenticationBackend()
    user = UserFactory(full_name="John Doe", short_name="John")

    def get_userinfo_mocked(*args):
        return {
            "sub": user.sub,
            "email": user.email,
            "first_name": "John",
            "last_name": "Doe",
        }

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    # Only 1 query because email and names have not changed
    with django_assert_num_queries(1):
        authenticated_user = klass.get_or_create_user(
            access_token="test-token", id_token=None, payload=None
        )

    assert user == authenticated_user


@pytest.mark.parametrize(
    "first_name, last_name, email",
    [
        ("Jack", "Doe", "john.doe@example.com"),
        ("John", "Duy", "john.doe@example.com"),
        ("John", "Doe", "jack.duy@example.com"),
        ("Jack", "Duy", "jack.duy@example.com"),
    ],
)
def test_authentication_getter_existing_user_change_fields_sub(
    first_name, last_name, email, django_assert_num_queries, monkeypatch
):
    """
    It should update the email or name fields on the user when they change
    and the user was identified by its "sub".
    """
    klass = OIDCAuthenticationBackend()
    user = UserFactory(full_name="John Doe", short_name="John", email="john.doe@example.com")

    def get_userinfo_mocked(*args):
        return {
            "sub": user.sub,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        }

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    # One and only one additional update query when a field has changed
    with django_assert_num_queries(3):  # user by sub, unicity check, update sub
        authenticated_user = klass.get_or_create_user(
            access_token="test-token", id_token=None, payload=None
        )

    assert user == authenticated_user
    user.refresh_from_db()
    assert user.email == email
    assert user.full_name == f"{first_name:s} {last_name:s}"
    assert user.short_name == first_name


@pytest.mark.parametrize(
    "first_name, last_name, email",
    [
        ("Jack", "Doe", "john.doe@example.com"),
        ("John", "Duy", "john.doe@example.com"),
    ],
)
def test_authentication_getter_existing_user_change_fields_email(
    first_name, last_name, email, django_assert_num_queries, monkeypatch
):
    """
    It should update the name fields on the user when they change
    and the user was identified by its "email" as fallback.
    """
    klass = OIDCAuthenticationBackend()
    user = UserFactory(full_name="John Doe", short_name="John", email="john.doe@example.com")

    def get_userinfo_mocked(*args):
        return {
            "sub": "123",
            "email": user.email,
            "first_name": first_name,
            "last_name": last_name,
        }

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    # One and only one additional update query when a field has changed
    with django_assert_num_queries(4):  # user by sub, user by mail, unicity check, update sub
        authenticated_user = klass.get_or_create_user(
            access_token="test-token", id_token=None, payload=None
        )

    assert user == authenticated_user
    user.refresh_from_db()
    assert user.email == email
    assert user.full_name == f"{first_name:s} {last_name:s}"
    assert user.short_name == first_name


def test_authentication_getter_new_user_no_email(monkeypatch):
    """
    If no user matches the user's info sub, a user should be created.
    User's info doesn't contain an email, created user's email should be empty.
    """
    klass = OIDCAuthenticationBackend()

    def get_userinfo_mocked(*args):
        return {"sub": "123"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user.sub == "123"
    assert user.email is None
    assert user.full_name is None
    assert user.short_name is None
    assert user.has_usable_password() is False
    assert models.User.objects.count() == 1


def test_authentication_getter_new_user_with_email(monkeypatch):
    """
    If no user matches the user's info sub, a user should be created.
    User's email and name should be set on the identity.
    The "email" field on the User model should not be set as it is reserved for staff users.
    """
    klass = OIDCAuthenticationBackend()

    email = "conversations@example.com"

    def get_userinfo_mocked(*args):
        return {"sub": "123", "email": email, "first_name": "John", "last_name": "Doe"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user.sub == "123"
    assert user.email == email
    assert user.full_name == "John Doe"
    assert user.short_name == "John"
    assert user.has_usable_password() is False
    assert models.User.objects.count() == 1


@responses.activate
def test_authentication_get_userinfo_json_response():
    """Test get_userinfo method with a JSON response."""

    responses.add(
        responses.GET,
        re.compile(r".*/userinfo"),
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        },
        status=200,
    )

    oidc_backend = OIDCAuthenticationBackend()
    result = oidc_backend.get_userinfo("fake_access_token", None, None)

    assert result["first_name"] == "John"
    assert result["last_name"] == "Doe"
    assert result["email"] == "john.doe@example.com"


@responses.activate
def test_authentication_get_userinfo_token_response(monkeypatch, settings):
    """Test get_userinfo method with a token response."""
    settings.OIDC_RP_SIGN_ALGO = "HS256"  # disable JWKS URL call
    responses.add(
        responses.GET,
        re.compile(r".*/userinfo"),
        body="fake.jwt.token",
        status=200,
        content_type="application/jwt",
    )

    def mock_verify_token(self, token):  # pylint: disable=unused-argument
        return {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@example.com",
        }

    monkeypatch.setattr(OIDCAuthenticationBackend, "verify_token", mock_verify_token)

    oidc_backend = OIDCAuthenticationBackend()
    result = oidc_backend.get_userinfo("fake_access_token", None, None)

    assert result["first_name"] == "Jane"
    assert result["last_name"] == "Doe"
    assert result["email"] == "jane.doe@example.com"


@responses.activate
def test_authentication_get_userinfo_invalid_response(settings):
    """
    Test get_userinfo method with an invalid JWT response that
    causes verify_token to raise an error.
    """
    settings.OIDC_RP_SIGN_ALGO = "HS256"  # disable JWKS URL call
    responses.add(
        responses.GET,
        re.compile(r".*/userinfo"),
        body="fake.jwt.token",
        status=200,
        content_type="application/jwt",
    )

    oidc_backend = OIDCAuthenticationBackend()

    with pytest.raises(
        SuspiciousOperation,
        match="User info response was not valid JWT",
    ):
        oidc_backend.get_userinfo("fake_access_token", None, None)


def test_authentication_getter_existing_disabled_user_via_sub(
    django_assert_num_queries, monkeypatch
):
    """
    If an existing user matches the sub but is disabled,
    an error should be raised and a user should not be created.
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory(is_active=False)

    def get_userinfo_mocked(*args):
        return {
            "sub": db_user.sub,
            "email": db_user.email,
            "first_name": "John",
            "last_name": "Doe",
        }

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with (
        django_assert_num_queries(1),
        pytest.raises(SuspiciousOperation, match="User account is disabled"),
    ):
        klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert models.User.objects.count() == 1


def test_authentication_getter_existing_disabled_user_via_email(
    django_assert_num_queries, monkeypatch
):
    """
    If an existing user does not match the sub but matches the email and is disabled,
    an error should be raised and a user should not be created.
    """

    klass = OIDCAuthenticationBackend()
    db_user = UserFactory(is_active=False)

    def get_userinfo_mocked(*args):
        return {
            "sub": "random",
            "email": db_user.email,
            "first_name": "John",
            "last_name": "Doe",
        }

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with (
        django_assert_num_queries(2),
        pytest.raises(SuspiciousOperation, match="User account is disabled"),
    ):
        klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert models.User.objects.count() == 1


@responses.activate
def test_authentication_session_tokens(django_assert_num_queries, monkeypatch, rf, settings):
    """
    Test that the session contains oidc_refresh_token and oidc_access_token after authentication.
    """
    settings.OIDC_STORE_ACCESS_TOKEN = True
    settings.OIDC_STORE_REFRESH_TOKEN = True
    settings.OIDC_STORE_REFRESH_TOKEN_KEY = Fernet.generate_key()

    klass = OIDCAuthenticationBackend()
    request = rf.get("/some-url", {"state": "test-state", "code": "test-code"})
    request.session = {}

    def verify_token_mocked(*args, **kwargs):
        return {"sub": "123", "email": "test@example.com"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "verify_token", verify_token_mocked)

    responses.add(
        responses.POST,
        re.compile(settings.OIDC_OP_TOKEN_ENDPOINT),
        json={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
        },
        status=200,
    )

    responses.add(
        responses.GET,
        re.compile(settings.OIDC_OP_USER_ENDPOINT),
        json={"sub": "123", "email": "test@example.com"},
        status=200,
    )

    with django_assert_num_queries(5):
        user = klass.authenticate(
            request,
            code="test-code",
            nonce="test-nonce",
            code_verifier="test-code-verifier",
        )

    assert user is not None
    assert request.session["oidc_access_token"] == "test-access-token"
    assert get_oidc_refresh_token(request.session) == "test-refresh-token"


@responses.activate
def test_authentication_user_added_to_brevo(monkeypatch, rf, settings):
    """
    Test that a user is added to the Brevo follow-up list upon authentication.
    """

    settings.BREVO_API_KEY = "test-api-key"
    settings.BREVO_FOLLOWUP_LIST_ID = "follow-up-list-id"

    brevo_create_contact = responses.post(
        "https://api.brevo.com/v3/contacts",
        status=200,
    )
    brevo_add_to_list = responses.post(
        "https://api.brevo.com/v3/contacts/lists/follow-up-list-id/contacts/add",
        status=400,
    )

    klass = OIDCAuthenticationBackend()
    request = rf.get("/some-url", {"state": "test-state", "code": "test-code"})
    request.session = {}

    def verify_token_mocked(*args, **kwargs):
        return {"sub": "123", "email": "test@example.com"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "verify_token", verify_token_mocked)

    responses.add(
        responses.POST,
        re.compile(settings.OIDC_OP_TOKEN_ENDPOINT),
        json={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
        },
        status=200,
    )

    responses.add(
        responses.GET,
        re.compile(settings.OIDC_OP_USER_ENDPOINT),
        json={"sub": "123", "email": "test@example.com"},
        status=200,
    )

    user = klass.authenticate(
        request,
        code="test-code",
        nonce="test-nonce",
        code_verifier="test-code-verifier",
    )

    assert len(brevo_create_contact.calls) == 1
    assert brevo_create_contact.calls[0].request.headers["api-key"] == "test-api-key"
    assert json.loads(brevo_create_contact.calls[0].request.body) == {
        "email": user.email,
        "updateEnabled": True,
    }

    assert len(brevo_add_to_list.calls) == 1
    assert brevo_add_to_list.calls[0].request.headers["api-key"] == "test-api-key"
    assert json.loads(brevo_add_to_list.calls[0].request.body) == {"emails": [user.email]}

    # Now test when activation is required: user should not be added to Brevo list
    settings.ACTIVATION_REQUIRED = True
    klass.authenticate(
        request,
        code="test-code",
        nonce="test-nonce",
        code_verifier="test-code-verifier",
    )

    assert len(brevo_create_contact.calls) == 1  # No new call made
    assert len(brevo_add_to_list.calls) == 1  # No new call made


@responses.activate
def test_authentication_user_not_added_to_brevo_without_list_id(monkeypatch, rf, settings):
    """
    Test that no Brevo call is made when BREVO_FOLLOWUP_LIST_ID is not configured.
    """

    settings.BREVO_API_KEY = "test-api-key"

    brevo_create_contact = responses.post(
        "https://api.brevo.com/v3/contacts",
        status=200,
    )

    klass = OIDCAuthenticationBackend()
    request = rf.get("/some-url", {"state": "test-state", "code": "test-code"})
    request.session = {}

    def verify_token_mocked(*args, **kwargs):
        return {"sub": "123", "email": "test@example.com"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "verify_token", verify_token_mocked)

    responses.add(
        responses.POST,
        re.compile(settings.OIDC_OP_TOKEN_ENDPOINT),
        json={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
        },
        status=200,
    )

    responses.add(
        responses.GET,
        re.compile(settings.OIDC_OP_USER_ENDPOINT),
        json={"sub": "123", "email": "test@example.com"},
        status=200,
    )

    user = klass.authenticate(
        request,
        code="test-code",
        nonce="test-nonce",
        code_verifier="test-code-verifier",
    )

    assert user is not None
    assert len(brevo_create_contact.calls) == 0


@responses.activate
def test_authentication_role_denied_user_not_added_to_brevo(monkeypatch, rf, settings):
    """
    Test that a user denied by the role gate is not added to the Brevo list.
    """

    settings.BREVO_API_KEY = "test-api-key"
    settings.BREVO_FOLLOWUP_LIST_ID = "follow-up-list-id"
    settings.OIDC_ALLOWED_ROLES = ["agent_public_etat"]

    brevo_create_contact = responses.post(
        "https://api.brevo.com/v3/contacts",
        status=200,
    )
    brevo_add_to_list = responses.post(
        "https://api.brevo.com/v3/contacts/lists/follow-up-list-id/contacts/add",
        status=200,
    )

    klass = OIDCAuthenticationBackend()
    request = rf.get("/some-url", {"state": "test-state", "code": "test-code"})
    request.session = {}

    def verify_token_mocked(*args, **kwargs):
        return {"sub": "123", "email": "test@example.com", "roles": ["user"]}

    monkeypatch.setattr(OIDCAuthenticationBackend, "verify_token", verify_token_mocked)

    responses.add(
        responses.POST,
        re.compile(settings.OIDC_OP_TOKEN_ENDPOINT),
        json={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
        },
        status=200,
    )

    responses.add(
        responses.GET,
        re.compile(settings.OIDC_OP_USER_ENDPOINT),
        json={"sub": "123", "email": "test@example.com", "roles": ["user"]},
        status=200,
    )

    with pytest.raises(OIDCRoleAccessDenied):
        klass.authenticate(
            request,
            code="test-code",
            nonce="test-nonce",
            code_verifier="test-code-verifier",
        )

    assert len(brevo_create_contact.calls) == 0
    assert len(brevo_add_to_list.calls) == 0


def test_verify_claims_no_allowed_roles_setting_allows_any_user():
    """With OIDC_ALLOWED_ROLES empty, any user passing essential claims is allowed."""
    klass = OIDCAuthenticationBackend()

    assert klass.verify_claims({"sub": "123"}) is True


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_user_with_required_role_allowed():
    """A user whose 'roles' claim contains a required role is allowed."""
    klass = OIDCAuthenticationBackend()

    assert klass.verify_claims({"sub": "123", "roles": ["other", "agent_public_etat"]}) is True


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_user_without_required_role_denied():
    """A user whose 'roles' claim lacks every required role is denied."""
    klass = OIDCAuthenticationBackend()

    with pytest.raises(OIDCRoleAccessDenied):
        klass.verify_claims({"sub": "123", "roles": ["other"]})


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_user_without_roles_claim_denied():
    """A user with no 'roles' claim at all is denied when a role is required."""
    klass = OIDCAuthenticationBackend()

    with pytest.raises(OIDCRoleAccessDenied):
        klass.verify_claims({"sub": "123"})


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_bypass_allows_user_without_role():
    """A role-less user whose email is on the active bypass list is allowed."""
    AccessBypassEmailFactory(email="bypass@example.com")
    klass = OIDCAuthenticationBackend()

    assert (
        klass.verify_claims({"sub": "123", "email": "bypass@example.com", "roles": ["user"]})
        is True
    )


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_bypass_is_case_insensitive():
    """The bypass match ignores email casing."""
    AccessBypassEmailFactory(email="bypass@example.com")
    klass = OIDCAuthenticationBackend()

    assert (
        klass.verify_claims({"sub": "123", "email": "ByPass@Example.COM", "roles": ["user"]})
        is True
    )


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_inactive_bypass_is_denied():
    """An inactive bypass entry does not grant access."""
    AccessBypassEmailFactory(email="bypass@example.com", is_active=False)
    klass = OIDCAuthenticationBackend()

    with pytest.raises(OIDCRoleAccessDenied):
        klass.verify_claims({"sub": "123", "email": "bypass@example.com", "roles": ["user"]})


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_expired_bypass_is_denied():
    """An expired bypass entry does not grant access."""
    AccessBypassEmailFactory(
        email="bypass@example.com",
        expires_at=timezone.now() - timedelta(days=1),
    )
    klass = OIDCAuthenticationBackend()

    with pytest.raises(OIDCRoleAccessDenied):
        klass.verify_claims({"sub": "123", "email": "bypass@example.com", "roles": ["user"]})


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_future_expiry_bypass_is_allowed():
    """A bypass entry with a future expiry still grants access."""
    AccessBypassEmailFactory(
        email="bypass@example.com",
        expires_at=timezone.now() + timedelta(days=1),
    )
    klass = OIDCAuthenticationBackend()

    assert (
        klass.verify_claims({"sub": "123", "email": "bypass@example.com", "roles": ["user"]})
        is True
    )


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_verify_claims_email_not_on_bypass_is_denied():
    """A role-less user whose email is not on the bypass list is denied."""
    AccessBypassEmailFactory(email="someone-else@example.com")
    klass = OIDCAuthenticationBackend()

    with pytest.raises(OIDCRoleAccessDenied):
        klass.verify_claims({"sub": "123", "email": "bypass@example.com", "roles": ["user"]})


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_existing_user_who_lost_required_role_is_denied_on_signin(monkeypatch):
    """An already-onboarded user whose role was revoked is denied at sign-in.

    The role is re-checked on every authentication: ``verify_claims`` runs
    before the existing-user lookup, so signing up with the role does not
    grandfather access once the role is removed in the IdP.
    """
    klass = OIDCAuthenticationBackend()
    db_user = UserFactory()

    def get_userinfo_mocked(*args):
        return {"sub": db_user.sub, "email": db_user.email, "roles": ["user"]}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    with pytest.raises(OIDCRoleAccessDenied):
        klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)


@override_settings(OIDC_ALLOWED_ROLES=["agent_public_etat"])
def test_existing_user_who_lost_role_but_on_bypass_can_signin(monkeypatch):
    """A role-revoked existing user is still let in if on the bypass list."""
    klass = OIDCAuthenticationBackend()
    db_user = UserFactory()
    AccessBypassEmailFactory(email=db_user.email)

    def get_userinfo_mocked(*args):
        return {"sub": db_user.sub, "email": db_user.email, "roles": ["user"]}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user == db_user


def test_get_extra_claims_maps_siret_to_organization_siret():
    """The 'siret' claim is exposed as the 'organization_siret' user field."""
    klass = OIDCAuthenticationBackend()

    extra = klass.get_extra_claims({"sub": "123", "siret": "12345678901234"})

    assert extra["organization_siret"] == "12345678901234"


def test_get_extra_claims_without_siret_is_empty():
    """A missing 'siret' claim maps to an empty string rather than raising."""
    klass = OIDCAuthenticationBackend()

    extra = klass.get_extra_claims({"sub": "123"})

    assert extra["organization_siret"] == ""


def test_get_extra_claims_strips_surrounding_whitespace_from_siret():
    """A well-formed SIRET with surrounding whitespace is stored trimmed."""
    klass = OIDCAuthenticationBackend()

    extra = klass.get_extra_claims({"sub": "123", "siret": "  12345678901234  "})

    assert extra["organization_siret"] == "12345678901234"


@pytest.mark.parametrize("value", ["123", "1234567890123A", "1234 5678 9012 34", ""])
def test_get_extra_claims_drops_malformed_siret(value):
    """A SIRET that is not exactly 14 digits maps to an empty string."""
    klass = OIDCAuthenticationBackend()

    extra = klass.get_extra_claims({"sub": "123", "siret": value})

    assert extra["organization_siret"] == ""


def test_signin_stores_siret_on_new_user(monkeypatch):
    """A new user signing in with a 'siret' claim gets it stored."""
    klass = OIDCAuthenticationBackend()

    def get_userinfo_mocked(*args):
        return {"sub": "new-sub", "email": "new@example.com", "siret": "12345678901234"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user.organization_siret == "12345678901234"


def test_signin_without_siret_does_not_break(monkeypatch):
    """Signing in without a 'siret' claim succeeds and leaves the field empty."""
    klass = OIDCAuthenticationBackend()

    def get_userinfo_mocked(*args):
        return {"sub": "new-sub", "email": "new@example.com"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user.organization_siret == ""


def test_existing_user_siret_is_refreshed_on_signin(monkeypatch):
    """A changed 'siret' claim updates the stored value on the next login."""
    klass = OIDCAuthenticationBackend()
    db_user = UserFactory(organization_siret="11111111111111")

    def get_userinfo_mocked(*args):
        return {"sub": db_user.sub, "email": db_user.email, "siret": "22222222222222"}

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", get_userinfo_mocked)

    user = klass.get_or_create_user(access_token="test-token", id_token=None, payload=None)

    assert user.organization_siret == "22222222222222"
