"""Tests for activation_codes permissions."""

from django.test import RequestFactory

import pytest
from rest_framework.views import APIView

from core.factories import UserFactory

from activation_codes.factories import UserActivationFactory
from activation_codes.permissions import IsActivatedUser


@pytest.fixture(name="request_factory")
def request_factory_fixture():
    """Fixture to provide a request factory."""
    return RequestFactory()


@pytest.fixture(name="view")
def view_fixture():
    """Fixture to provide a basic view instance."""
    return APIView()


@pytest.mark.django_db
def test_is_activated_user_permission_activation_not_required(request_factory, view, settings):
    """Test that permission allows access when activation is not required."""
    settings.ACTIVATION_REQUIRED = False
    user = UserFactory()

    request = request_factory.get("/")
    request.user = user

    permission = IsActivatedUser()
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_is_activated_user_permission_staff_user(request_factory, view, settings):
    """Test that staff users always have permission."""
    settings.ACTIVATION_REQUIRED = True
    staff_user = UserFactory(email="staff@example.com", password="password123", is_staff=True)

    request = request_factory.get("/")
    request.user = staff_user

    permission = IsActivatedUser()
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_is_activated_user_permission_anonymous_user(request_factory, view, settings):
    """Test that anonymous users are allowed (handled by other permissions)."""
    settings.ACTIVATION_REQUIRED = True

    request = request_factory.get("/")
    request.user = None

    permission = IsActivatedUser()
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_is_activated_user_permission_activated_user(request_factory, view, settings):
    """Test that activated users have permission."""
    settings.ACTIVATION_REQUIRED = True

    # Activate the user
    activation = UserActivationFactory()

    request = request_factory.get("/")
    request.user = activation.user

    permission = IsActivatedUser()
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_is_activated_user_permission_not_activated_user(request_factory, view, settings):
    """Test that non-activated users do not have permission."""
    settings.ACTIVATION_REQUIRED = True

    user = UserFactory()

    request = request_factory.get("/")
    request.user = user

    permission = IsActivatedUser()
    assert permission.has_permission(request, view) is False


@pytest.mark.django_db
def test_is_activated_user_permission_custom_message():
    """Test that permission has custom message for frontend."""
    permission = IsActivatedUser()
    assert permission.message == "activation-required"


@pytest.mark.django_db
def test_is_activated_user_object_permission(request_factory, view, settings):
    """Test object-level permission delegates to has_permission."""
    settings.ACTIVATION_REQUIRED = True

    _user = UserFactory()

    # Activate the user
    activation = UserActivationFactory()

    request = request_factory.get("/")
    request.user = activation.user

    permission = IsActivatedUser()
    obj = object()  # Any object

    # Object permission should delegate to has_permission
    assert permission.has_object_permission(request, view, obj) is True


@pytest.mark.django_db
def test_is_activated_user_object_permission_not_activated(request_factory, view, settings):
    """Test object-level permission when user is not activated."""
    settings.ACTIVATION_REQUIRED = True

    user = UserFactory()

    request = request_factory.get("/")
    request.user = user

    permission = IsActivatedUser()
    obj = object()

    assert permission.has_object_permission(request, view, obj) is False
