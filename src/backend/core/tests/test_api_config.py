"""
Test config API endpoints in the Conversations core app.
"""

import datetime
import json

from django.test import AsyncClient, override_settings

import pytest
from asgiref.sync import sync_to_async
from freezegun import freeze_time
from rest_framework.status import (
    HTTP_200_OK,
)
from rest_framework.test import APIClient

from core import factories, models

pytestmark = pytest.mark.django_db


@override_settings(
    FRONTEND_CONTACT_EMAIL="contact@test.com",
    STATUS_PAGE_URL="https://status.example.com",
    FRONTEND_CSS_URL="http://testcss/",
    FRONTEND_DOCUMENTATION_URL="http://testdocs/",
    FRONTEND_THEME="test-theme",
    MEDIA_BASE_URL="http://testserver/",
    POSTHOG_KEY={"id": "132456", "host": "https://eu.i.posthog-test.com"},
    SENTRY_DSN="https://sentry.test/123",
    THEME_CUSTOMIZATION_FILE_PATH="",
    RAG_FILES_ACCEPTED_FORMATS=[
        "application/pdf",
        "text/plain",
    ],
)
@pytest.mark.parametrize("is_authenticated", [False, True])
def test_api_config(is_authenticated):
    """Anonymous users should be allowed to get the configuration."""
    client = APIClient()

    if is_authenticated:
        user = factories.UserFactory()
        client.force_login(user)

    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "ACTIVATION_REQUIRED": False,
        "STATUS_PAGE_URL": "https://status.example.com",
        "DOCS_BASE_URL": None,
        "ENVIRONMENT": "test",
        "FEATURE_FLAGS": {"document-upload": "enabled", "web-search": "enabled"},
        "FILE_UPLOAD_MODE": "presigned_url",
        "FRONTEND_CONTACT_EMAIL": "contact@test.com",
        "FRONTEND_CSS_URL": "http://testcss/",
        "FRONTEND_DOCUMENTATION_URL": "http://testdocs/",
        "FRONTEND_HOMEPAGE_FEATURE_ENABLED": True,
        "FRONTEND_SILENT_LOGIN_ENABLED": True,
        "FRONTEND_THEME": "test-theme",
        "LANGUAGES": [
            ["en-us", "English"],
            ["fr-fr", "Français"],
            # ["de-de", "Deutsch"],
            ["nl-nl", "Nederlands"],
            # ["es-es", "Español"],
        ],
        "LANGUAGE_CODE": "en-us",
        "MEDIA_BASE_URL": "http://testserver/",
        "POSTHOG_KEY": {"id": "132456", "host": "https://eu.i.posthog-test.com"},
        "SENTRY_DSN": "https://sentry.test/123",
        "theme_customization": {},
        "chat_upload_accept": "application/pdf,text/plain",        
        "project_files_max_count": 10,
        "project_images_max_count": 3,
        "attachment_max_size": 10,
        "status_banner": None,
        "maintenance": None,
    }


@override_settings(FRONTEND_CONTACT_EMAIL=None, FRONTEND_DOCUMENTATION_URL=None)
def test_api_config_help_links_unset():
    """Documentation URL and contact email are exposed as None when not configured."""
    response = APIClient().get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    content = response.json()
    assert content["FRONTEND_CONTACT_EMAIL"] is None
    assert content["FRONTEND_DOCUMENTATION_URL"] is None


@override_settings(DOCS_BASE_URL="http://docs.example.com/")
def test_api_config_exposes_docs_base_url():
    """DOCS_BASE_URL must be present in the config response when configured."""
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["DOCS_BASE_URL"] == "http://docs.example.com/"


@override_settings(DOCS_BASE_URL=None)
def test_api_config_docs_base_url_none_when_not_configured():
    """DOCS_BASE_URL must be null in the config response when not configured."""
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["DOCS_BASE_URL"] is None


@override_settings(DOCS_BASE_URL="http://docs.example.com/")
def test_api_config_exposes_docs_base_url():
    """DOCS_BASE_URL must be present in the config response when configured."""
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["DOCS_BASE_URL"] == "http://docs.example.com/"


@override_settings(DOCS_BASE_URL=None)
def test_api_config_docs_base_url_none_when_not_configured():
    """DOCS_BASE_URL must be null in the config response when not configured."""
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["DOCS_BASE_URL"] is None


@override_settings(
    THEME_CUSTOMIZATION_FILE_PATH="/not/existing/file.json",
)
@pytest.mark.parametrize("is_authenticated", [False, True])
def test_api_config_with_invalid_theme_customization_file(is_authenticated):
    """Anonymous users should be allowed to get the configuration."""
    client = APIClient()

    if is_authenticated:
        user = factories.UserFactory()
        client.force_login(user)

    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    content = response.json()
    assert content["theme_customization"] == {}


@override_settings(
    THEME_CUSTOMIZATION_FILE_PATH="/configuration/theme/invalid.json",
)
@pytest.mark.parametrize("is_authenticated", [False, True])
def test_api_config_with_invalid_json_theme_customization_file(is_authenticated, fs):
    """Anonymous users should be allowed to get the configuration."""
    fs.create_file(
        "/configuration/theme/invalid.json",
        contents="invalid json",
    )
    client = APIClient()

    if is_authenticated:
        user = factories.UserFactory()
        client.force_login(user)

    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    content = response.json()
    assert content["theme_customization"] == {}


@override_settings(
    THEME_CUSTOMIZATION_FILE_PATH="/configuration/theme/default.json",
)
@pytest.mark.parametrize("is_authenticated", [False, True])
def test_api_config_with_theme_customization(is_authenticated, fs):
    """Anonymous users should be allowed to get the configuration."""
    fs.create_file(
        "/configuration/theme/default.json",
        contents=json.dumps(
            {
                "colors": {
                    "primary": "#000000",
                    "secondary": "#000000",
                },
            }
        ),
    )
    client = APIClient()

    if is_authenticated:
        user = factories.UserFactory()
        client.force_login(user)

    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    content = response.json()
    assert content["theme_customization"] == {
        "colors": {
            "primary": "#000000",
            "secondary": "#000000",
        },
    }


@pytest.mark.parametrize("is_authenticated", [False, True])
def test_api_config_with_original_theme_customization(is_authenticated, settings):
    """Anonymous users should be allowed to get the configuration."""
    client = APIClient()

    if is_authenticated:
        user = factories.UserFactory()
        client.force_login(user)

    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    content = response.json()

    with open(settings.THEME_CUSTOMIZATION_FILE_PATH, "r", encoding="utf-8") as f:
        theme_customization = json.load(f)

    assert content["theme_customization"] == theme_customization


@override_settings(
    FRONTEND_CONTACT_EMAIL="contact@test.com",
    STATUS_PAGE_URL="https://status.example.com",
    FRONTEND_CSS_URL="http://testcss/",
    FRONTEND_DOCUMENTATION_URL="http://testdocs/",
    FRONTEND_THEME="test-theme",
    MEDIA_BASE_URL="http://testserver/",
    POSTHOG_KEY={"id": "132456", "host": "https://eu.i.posthog-test.com"},
    SENTRY_DSN="https://sentry.test/123",
    THEME_CUSTOMIZATION_FILE_PATH="",
    RAG_FILES_ACCEPTED_FORMATS=[
        "application/pdf",
        "text/plain",
    ],
)
@pytest.mark.asyncio
@pytest.mark.parametrize("is_authenticated", [False, True])
async def test_api_config_async(is_authenticated):
    """Anonymous users should be allowed to get the configuration (async client)."""
    client = AsyncClient()

    if is_authenticated:
        user = await sync_to_async(factories.UserFactory)()
        await client.aforce_login(user)

    response = await client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "ACTIVATION_REQUIRED": False,
        "STATUS_PAGE_URL": "https://status.example.com",
        "DOCS_BASE_URL": None,
        "ENVIRONMENT": "test",
        "FEATURE_FLAGS": {"document-upload": "enabled", "web-search": "enabled"},
        "FILE_UPLOAD_MODE": "presigned_url",
        "FRONTEND_CONTACT_EMAIL": "contact@test.com",
        "FRONTEND_CSS_URL": "http://testcss/",
        "FRONTEND_DOCUMENTATION_URL": "http://testdocs/",
        "FRONTEND_HOMEPAGE_FEATURE_ENABLED": True,
        "FRONTEND_SILENT_LOGIN_ENABLED": True,
        "FRONTEND_THEME": "test-theme",
        "LANGUAGES": [
            ["en-us", "English"],
            ["fr-fr", "Français"],
            # ["de-de", "Deutsch"],
            ["nl-nl", "Nederlands"],
            # ["es-es", "Español"],
        ],
        "LANGUAGE_CODE": "en-us",
        "MEDIA_BASE_URL": "http://testserver/",
        "POSTHOG_KEY": {"id": "132456", "host": "https://eu.i.posthog-test.com"},
        "SENTRY_DSN": "https://sentry.test/123",
        "theme_customization": {},
        "chat_upload_accept": "application/pdf,text/plain",
        "project_files_max_count": 10,
        "project_images_max_count": 3,
        "attachment_max_size": 10,
        "status_banner": None,
        "maintenance": None,
    }


@override_settings(
    STATUS_PAGE_URL=None,
    THEME_CUSTOMIZATION_FILE_PATH="",
    RAG_FILES_ACCEPTED_FORMATS=["application/pdf"],
)
def test_api_config_albert_status_page_url_none():
    """STATUS_PAGE_URL defaults to None and is included in config."""
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["STATUS_PAGE_URL"] is None


@override_settings(
    STATUS_PAGE_URL="https://status.example.com",
    THEME_CUSTOMIZATION_FILE_PATH="",
    RAG_FILES_ACCEPTED_FORMATS=["application/pdf"],
)
def test_api_config_albert_status_page_url_set():
    """STATUS_PAGE_URL is propagated to the config endpoint when set."""
    client = APIClient()
    response = client.get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["STATUS_PAGE_URL"] == "https://status.example.com"


def _set_banner(**fields):
    config = models.SiteConfiguration.get_solo()
    for field, value in fields.items():
        setattr(config, field, value)
    config.save()
    return config


def test_api_config_status_banner_not_configured():
    """Empty title means no banner is returned."""
    _set_banner(
        status_banner_level=models.BannerLevelChoice.WARNING,
        status_banner_title="",
        status_banner_content="abcd",
    )
    response = APIClient().get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["status_banner"] is None


def test_api_config_status_banner_configured_without_window():
    """A configured banner with no time window is always returned."""
    _set_banner(
        status_banner_level=models.BannerLevelChoice.WARNING,
        status_banner_title="Ongoing technical issue",
        status_banner_content="We are working on it.",
    )
    response = APIClient().get("/api/v1.0/config/")
    assert response.status_code == HTTP_200_OK
    assert response.json()["status_banner"] == {
        "level": "warning",
        "title": "Ongoing technical issue",
        "content": "We are working on it.",
    }


def test_api_config_status_banner_title_only():
    """Title alone is enough to enable the banner."""
    _set_banner(
        status_banner_level=models.BannerLevelChoice.INFO,
        status_banner_title="Heads up",
        status_banner_content="",
    )
    response = APIClient().get("/api/v1.0/config/")
    assert response.json()["status_banner"] == {
        "level": "info",
        "title": "Heads up",
        "content": "",
    }


@freeze_time("2026-05-11T12:00:00Z")
def test_api_config_status_banner_hidden_before_start():
    """starts_at in the future hides the banner."""
    _set_banner(
        status_banner_level=models.BannerLevelChoice.WARNING,
        status_banner_title="Scheduled maintenance",
        status_banner_content="Coming up.",
        status_banner_starts_at=datetime.datetime(2026, 5, 11, 13, 0, tzinfo=datetime.timezone.utc),
    )
    response = APIClient().get("/api/v1.0/config/")
    assert response.json()["status_banner"] is None


@freeze_time("2026-05-11T12:00:00Z")
def test_api_config_status_banner_visible_after_start():
    """starts_at in the past keeps the banner visible."""
    _set_banner(
        status_banner_level=models.BannerLevelChoice.WARNING,
        status_banner_title="Ongoing",
        status_banner_content="lorem ipsum",
        status_banner_starts_at=datetime.datetime(2026, 5, 11, 11, 0, tzinfo=datetime.timezone.utc),
    )
    response = APIClient().get("/api/v1.0/config/")
    assert response.json()["status_banner"] is not None


@freeze_time("2026-05-11T12:00:00Z")
def test_api_config_status_banner_hidden_after_end():
    """ends_at in the past hides the banner."""
    _set_banner(
        status_banner_level=models.BannerLevelChoice.WARNING,
        status_banner_title="Old",
        status_banner_content="lorem ipsum",
        status_banner_ends_at=datetime.datetime(2026, 5, 11, 11, 0, tzinfo=datetime.timezone.utc),
    )
    response = APIClient().get("/api/v1.0/config/")
    assert response.json()["status_banner"] is None


@freeze_time("2026-05-11T12:00:00Z")
def test_api_config_status_banner_visible_before_end():
    """ends_at in the future keeps the banner visible."""
    _set_banner(
        status_banner_level=models.BannerLevelChoice.WARNING,
        status_banner_title="Still on",
        status_banner_content="lorem ipsum",
        status_banner_ends_at=datetime.datetime(2026, 5, 11, 13, 0, tzinfo=datetime.timezone.utc),
    )
    response = APIClient().get("/api/v1.0/config/")
    assert response.json()["status_banner"] is not None


@pytest.mark.parametrize(
    "now_offset_hours,expected_visible",
    [
        (-2, False),  # before window
        (0, True),  # inside window
        (+4, False),  # after window
    ],
)
def test_api_config_status_banner_window(now_offset_hours, expected_visible):
    """Both bounds set: visible only inside the window."""
    base = datetime.datetime(2026, 5, 11, 12, 0, tzinfo=datetime.timezone.utc)
    _set_banner(
        status_banner_level=models.BannerLevelChoice.ALERT,
        status_banner_title="Window",
        status_banner_content="lorem ipsum",
        status_banner_starts_at=base + datetime.timedelta(hours=-1),
        status_banner_ends_at=base + datetime.timedelta(hours=+1),
    )
    with freeze_time(base + datetime.timedelta(hours=now_offset_hours)):
        response = APIClient().get("/api/v1.0/config/")
    if expected_visible:
        assert response.json()["status_banner"] is not None
    else:
        assert response.json()["status_banner"] is None
