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


class ChatProjectAttachmentFactory(factory.django.DjangoModelFactory):
    """Factory for creating project-scoped attachment instances."""

    conversation = None
    project = factory.SubFactory(ChatProjectFactory)
    uploaded_by = factory.SubFactory(UserFactory)
    key = factory.LazyAttribute(
        lambda obj: f"{obj.project.pk}/attachments/{uuid4()}.{obj.file_name.split('.')[-1]}"
    )
    file_name = factory.Faker("file_name")
    content_type = factory.Faker("mime_type")

    class Meta:
        model = models.ChatConversationAttachment


class ArenaExperimentFactory(factory.django.DjangoModelFactory):
    """Factory for arena experiments (inactive by default, champion = default model)."""

    name = factory.Sequence(lambda n: f"experiment {n}")
    is_active = False
    sampling_rate = 1.0
    daily_cap_per_user = 100

    class Meta:
        model = models.ArenaExperiment


class ArenaChallengerFactory(factory.django.DjangoModelFactory):
    """Factory for arena challengers."""

    experiment = factory.SubFactory(ArenaExperimentFactory)
    model_hrid = "challenger-model"

    class Meta:
        model = models.ArenaChallenger


class ArenaComparisonFactory(factory.django.DjangoModelFactory):
    """Factory for arena comparisons, pending with the champion on the left by default."""

    experiment = factory.SubFactory(ArenaExperimentFactory)
    conversation = factory.SubFactory(ChatConversationFactory)
    user = factory.LazyAttribute(lambda obj: obj.conversation.owner)
    champion_model_hrid = factory.LazyAttribute(lambda obj: obj.experiment.champion_model_hrid)
    challenger_model_hrid = "challenger-model"
    champion_side = "left"

    class Meta:
        model = models.ArenaComparison
