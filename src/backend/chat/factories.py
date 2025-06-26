"""Factories for chat application."""

import factory.django

from core.factories import UserFactory

from . import models


class ChatConversationFactory(factory.django.DjangoModelFactory):
    """Factory for creating ChatConversation instances."""

    owner = factory.SubFactory(UserFactory)

    class Meta:
        model = models.ChatConversation
