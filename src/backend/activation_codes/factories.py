"""Factories for creating activation code and user activation instances for testing."""

from django.utils import timezone

import factory.django

from core.factories import UserFactory

from . import models


class ActivationCodeFactory(factory.django.DjangoModelFactory):
    """A factory to create activation codes for testing purposes."""

    class Meta:
        model = models.ActivationCode

    code = factory.LazyAttribute(lambda x: models.generate_activation_code())
    created_at = factory.LazyAttribute(lambda obj: timezone.now())


class UserActivationFactory(factory.django.DjangoModelFactory):
    """A factory to create user activations for testing purposes."""

    class Meta:
        model = models.UserActivation

    user = factory.SubFactory(UserFactory)
    activation_code = factory.SubFactory(ActivationCodeFactory)
