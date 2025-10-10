"""Factories for chat application."""

import factory.django

from core.factories import UserFactory

from . import models


class ChatConversationFactory(factory.django.DjangoModelFactory):
    """Factory for creating ChatConversation instances."""

    owner = factory.SubFactory(UserFactory)

    class Meta:
        model = models.ChatConversation


class ChatConversationAttachmentFactory(factory.django.DjangoModelFactory):
    """Factory for creating ChatConversationAttachment instances."""

    conversation = factory.SubFactory(ChatConversationFactory)
    uploaded_by = factory.SubFactory(UserFactory)
    key = factory.Faker("uuid4")
    file_name = factory.Faker("file_name")
    content_type = factory.Faker("mime_type")

    class Meta:
        model = models.ChatConversationAttachment
