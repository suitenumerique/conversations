"""Unit tests for the PostHog events reported by the project viewset."""

from unittest.mock import patch

import pytest

from core.factories import UserFactory

from chat.factories import ChatProjectFactory
from chat.models import ChatProject, ChatProjectColor, ChatProjectIcon

pytestmark = pytest.mark.django_db


@pytest.fixture(name="posthog_configured", autouse=True)
def posthog_configured_fixture(settings):
    """Configure PostHog so the capture guard lets the events through."""
    settings.POSTHOG_KEY = {"id": "key", "host": "https://posthog.test"}


def test_create_project_is_captured(api_client):
    """Creating a project reports it, without leaking the title."""
    user = UserFactory()
    api_client.force_login(user)

    with patch("core.analytics.posthog") as mock_posthog:
        response = api_client.post(
            "/api/v1.0/projects/",
            {
                "title": "Quarterly budget",
                "icon": ChatProjectIcon.FOLDER,
                "color": ChatProjectColor.COLOR_1,
                "llm_instructions": "Answer in French.",
            },
            format="json",
        )

    assert response.status_code == 201
    mock_posthog.capture.assert_called_once()
    call = mock_posthog.capture.call_args
    assert call.args[0] == "project_created"
    assert call.kwargs["distinct_id"] == str(user.pk)
    assert call.kwargs["properties"] == {
        "id": str(response.data["id"]),
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
        "has_instructions": True,
    }
    assert "Quarterly budget" not in str(call.kwargs["properties"])


def test_create_project_without_instructions_is_captured(api_client):
    """`has_instructions` distinguishes a bare project from a customised one."""
    user = UserFactory()
    api_client.force_login(user)

    with patch("core.analytics.posthog") as mock_posthog:
        response = api_client.post(
            "/api/v1.0/projects/",
            {
                "title": "Bare",
                "icon": ChatProjectIcon.FOLDER,
                "color": ChatProjectColor.COLOR_1,
            },
            format="json",
        )

    assert response.status_code == 201
    assert mock_posthog.capture.call_args.kwargs["properties"]["has_instructions"] is False


def test_update_project_is_captured(api_client):
    """Updating a project reports the state it ends up in."""
    project = ChatProjectFactory(icon=ChatProjectIcon.FOLDER, llm_instructions="")
    api_client.force_login(project.owner)

    with patch("core.analytics.posthog") as mock_posthog:
        response = api_client.patch(
            f"/api/v1.0/projects/{project.pk}/",
            {"llm_instructions": "Be concise."},
            format="json",
        )

    assert response.status_code == 200
    call = mock_posthog.capture.call_args
    assert call.args[0] == "project_updated"
    assert call.kwargs["properties"]["id"] == str(project.pk)
    assert call.kwargs["properties"]["has_instructions"] is True


def test_delete_project_is_captured(api_client):
    """A project that is really gone reports the identity it had."""
    project = ChatProjectFactory()
    api_client.force_login(project.owner)

    with patch("core.analytics.posthog") as mock_posthog:
        response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == 204
    assert not ChatProject.objects.filter(pk=project.pk).exists()
    call = mock_posthog.capture.call_args
    assert call.args[0] == "project_deleted"
    assert call.kwargs["distinct_id"] == str(project.owner.pk)
    assert call.kwargs["properties"]["id"] == str(project.pk)


def test_a_failed_delete_is_not_captured(api_client):
    """A project the database refused to drop must not report a deletion."""
    project = ChatProjectFactory()
    api_client.force_login(project.owner)

    with (
        patch("core.analytics.posthog") as mock_posthog,
        patch.object(ChatProject, "delete", side_effect=RuntimeError("delete failed")),
        pytest.raises(RuntimeError),
    ):
        api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    mock_posthog.capture.assert_not_called()


def test_nothing_is_captured_without_a_posthog_key(api_client, settings):
    """With PostHog unconfigured, the viewset must not reach for the SDK."""
    settings.POSTHOG_KEY = None
    user = UserFactory()
    api_client.force_login(user)

    with patch("core.analytics.posthog") as mock_posthog:
        response = api_client.post(
            "/api/v1.0/projects/",
            {
                "title": "Quiet",
                "icon": ChatProjectIcon.FOLDER,
                "color": ChatProjectColor.COLOR_1,
            },
            format="json",
        )

    assert response.status_code == 201
    mock_posthog.capture.assert_not_called()


def test_a_failing_capture_does_not_fail_the_request(api_client):
    """Analytics is never worth a 500: a broken capture is swallowed."""
    user = UserFactory()
    api_client.force_login(user)

    with patch("core.analytics.posthog") as mock_posthog:
        mock_posthog.capture.side_effect = RuntimeError("posthog is down")
        response = api_client.post(
            "/api/v1.0/projects/",
            {
                "title": "Resilient",
                "icon": ChatProjectIcon.FOLDER,
                "color": ChatProjectColor.COLOR_1,
            },
            format="json",
        )

    assert response.status_code == 201
