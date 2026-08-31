"""Unit tests for chat conversation creation in the chat API view."""

from unittest.mock import patch

from django.core.cache import cache

import pytest
from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.throttling import SimpleRateThrottle

from core.factories import UserFactory

from chat.factories import ChatConversationFactory, ChatProjectFactory
from chat.models import ChatConversation
from chat.tests.utils import throttle_rates

pytestmark = pytest.mark.django_db


def test_create_conversation(api_client):
    """Test creating a new chat conversation as an authenticated user."""
    user = UserFactory(sub="testuser", email="test@example.com")
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["title"] == "New Conversation"
    assert response.data["messages"] == []

    # Verify in database
    conversation = ChatConversation.objects.get(id=response.data["id"])
    assert conversation.owner == user
    assert conversation.title == "New Conversation"
    assert not conversation.title_set_by_user_at


def test_create_conversation_other_owner(api_client):
    """Test that a user cannot assign another user as the owner of a conversation."""
    other_user = UserFactory()

    user = UserFactory()
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
        "owner": str(other_user.pk),  # Attempt to set another user as owner
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED

    # Verify in database
    conversation = ChatConversation.objects.get(id=response.data["id"])
    assert conversation.owner == user
    assert conversation.title == "New Conversation"


def test_create_conversation_with_project(api_client):
    """Test creating a conversation attached to a project."""
    project = ChatProjectFactory()
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
        "project": str(project.pk),
    }
    api_client.force_login(project.owner)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert str(response.data["project"]) == str(project.pk)

    conversation = ChatConversation.objects.get(id=response.data["id"])
    assert conversation.project == project


def test_create_conversation_with_other_user_project_fails(api_client):
    """Test that creating a conversation with another user's project is rejected."""
    user = UserFactory()
    other_project = ChatProjectFactory()  # owned by another user
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
        "project": str(other_project.pk),
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    assert response.data == {
        "project": [
            ErrorDetail(
                string="The project must belong to the current user.",
                code="invalid",
            )
        ]
    }


def test_create_conversation_without_project(api_client):
    """Test creating a conversation without a project."""
    user = UserFactory()
    url = "/api/v1.0/chats/"
    data = {"title": "New Conversation"}
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["project"] is None


def test_create_conversation_anonymous(api_client):
    """Test creating a conversation as an anonymous user returns a 401 error."""
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
    }
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_conversation_throttled_over_the_hourly_rate(api_client):
    """The 21st conversation of the hour is rejected with a 429."""
    user = UserFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(user)

    for _ in range(20):
        assert (
            api_client.post(url, {"title": "ok"}, format="json").status_code
            == status.HTTP_201_CREATED
        )

    response = api_client.post(url, {"title": "too many"}, format="json")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.has_header("Retry-After")
    assert ChatConversation.objects.filter(owner=user).count() == 20


def test_create_conversation_throttled_over_the_daily_rate(api_client):
    """The daily rate rejects a user still well under the hourly one."""
    user = UserFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(user)

    with throttle_rates(conversation_create_hourly="100/hour", conversation_create_daily="3/day"):
        for _ in range(3):
            assert (
                api_client.post(url, {"title": "ok"}, format="json").status_code
                == status.HTTP_201_CREATED
            )
        response = api_client.post(url, {"title": "too many"}, format="json")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_create_conversation_throttle_is_per_user(api_client):
    """One user exhausting their rate does not block another."""
    url = "/api/v1.0/chats/"

    with throttle_rates(conversation_create_hourly="1/hour"):
        throttled_user = UserFactory()
        api_client.force_login(throttled_user)
        api_client.post(url, {"title": "ok"}, format="json")
        assert (
            api_client.post(url, {"title": "ok"}, format="json").status_code
            == status.HTTP_429_TOO_MANY_REQUESTS
        )

        other_user = UserFactory()
        api_client.force_login(other_user)
        response = api_client.post(url, {"title": "ok"}, format="json")

    assert response.status_code == status.HTTP_201_CREATED


def test_create_conversation_throttle_does_not_apply_to_reads(api_client):
    """Only creation is throttled: listing still works past the limit."""
    user = UserFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(user)
    ChatConversationFactory(owner=user)

    with throttle_rates(conversation_create_hourly="1/hour"):
        api_client.post(url, {"title": "ok"}, format="json")
        assert (
            api_client.post(url, {"title": "ok"}, format="json").status_code
            == status.HTTP_429_TOO_MANY_REQUESTS
        )

        assert api_client.get(url).status_code == status.HTTP_200_OK


def test_create_conversation_throttle_does_not_apply_to_updates(api_client):
    """Renaming a conversation is an update, not a creation: never throttled."""
    user = UserFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(user)
    conversation = ChatConversationFactory(owner=user)

    with throttle_rates(conversation_create_hourly="1/hour"):
        api_client.post(url, {"title": "ok"}, format="json")
        assert (
            api_client.post(url, {"title": "ok"}, format="json").status_code
            == status.HTTP_429_TOO_MANY_REQUESTS
        )

        detail_url = f"{url}{conversation.pk}/"
        patched = api_client.patch(detail_url, {"title": "renamed"}, format="json")
        put = api_client.put(detail_url, {"title": "renamed again"}, format="json")

    assert patched.status_code == status.HTTP_200_OK
    assert put.status_code == status.HTTP_200_OK
    conversation.refresh_from_db()
    assert conversation.title == "renamed again"


class LostUpdateCache:
    """A cache whose reads never see what an earlier request wrote back.

    Two workers racing on the same window both read its state as it was before
    either of them wrote: the second one's write is lost. Staging that
    interleaving is the only way to cover it here, because the suite runs
    single-process on LocMemCache, where the GIL lets a read-modify-write
    finish inside one switch interval. Production has neither protection --
    several worker processes, and a network round-trip to Redis sitting
    between the read and the write.
    """

    def __init__(self, inner):
        self._inner = inner

    def get(self, key, default=None, version=None):  # pylint: disable=unused-argument
        """Always miss, as a racing worker does before the other one writes."""
        return default

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_create_conversation_throttle_does_not_count_by_reading_back_its_writes(api_client):
    """The creation ceiling must hold even when a concurrent write is lost.

    A throttle that counts by reading its own history back cannot bound
    storage: this is the regression that ``AtomicWindowThrottle`` exists for.
    """
    user = UserFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(user)

    with throttle_rates(conversation_create_hourly="1/hour", conversation_create_daily="100/day"):
        with patch.object(SimpleRateThrottle, "cache", LostUpdateCache(cache)):
            first = api_client.post(url, {"title": "ok"}, format="json")
            second = api_client.post(url, {"title": "too many"}, format="json")

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert ChatConversation.objects.filter(owner=user).count() == 1
