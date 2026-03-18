"""Factories for chat application."""

from uuid import uuid4

import factory.django

from core.factories import UserFactory

from . import models


class ChatProjectFactory(factory.django.DjangoModelFactory):
    """Factory for creating Project instances."""

    title = factory.Sequence(lambda n: f"title {n}")
    owner = factory.SubFactory(UserFactory)
    icon = factory.fuzzy.FuzzyChoice(models.ChatProjectIcon)
    color = factory.fuzzy.FuzzyChoice(models.ChatProjectColor)

    class Meta:
        model = models.ChatProject
        skip_postgeneration_save = True

    @factory.post_generation
    def number_of_conversations(self, create, extracted, **kwargs):
        """Create attached conversations for the project."""
        if not create or not extracted:
            return

        if not isinstance(extracted, int):
            raise TypeError("number_of_conversations must be an integer")
        ChatConversationFactory.create_batch(extracted, project=self, owner=self.owner)


class ChatConversationFactory(factory.django.DjangoModelFactory):
    """Factory for creating ChatConversation instances."""

    owner = factory.SubFactory(UserFactory)

    class Meta:
        model = models.ChatConversation


class ChatConversationAttachmentFactory(factory.django.DjangoModelFactory):
    """Factory for creating ChatConversationAttachment instances."""

    conversation = factory.SubFactory(ChatConversationFactory)
    uploaded_by = factory.SubFactory(UserFactory)
    key = factory.LazyAttribute(
        lambda obj: f"{obj.conversation.pk}/attachments/{uuid4()}.{obj.file_name.split('.')[-1]}"
    )
    file_name = factory.Faker("file_name")
    content_type = factory.Faker("mime_type")

    class Meta:
        model = models.ChatConversationAttachment
