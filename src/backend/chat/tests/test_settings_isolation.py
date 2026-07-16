"""Guard tests ensuring the test settings are deterministic.

Tests run against a dedicated environment (``env.d/test``) loaded by the
``app-test`` compose service in docker and by pytest-dotenv on the host / in CI;
``env.d/development/common`` is never loaded. These tests fail loudly if that
mechanism breaks — either because a developer-local value leaks in (a setting no
longer resolves to Base's coded default) or because ``env.d/test`` is not loaded
(a setting it pins is missing).

``settings`` is pytest-django's fixture, which proxies to ``django.conf.settings``.
"""

import os


def test_env_test_file_is_loaded(settings):
    """Settings pinned in env.d/test must resolve to their test values."""
    assert settings.AI_MODEL == "test-model"
    assert settings.AI_API_KEY == "test-api-key"
    assert settings.AI_BASE_URL == "https://www.external-ai-service.com/"
    assert settings.ALBERT_API_KEY == "test-key"
    assert settings.SECRET_KEY


def test_no_developer_env_leaks_into_tests(settings):
    """Behavior settings absent from env.d/test must use Base's coded default.

    A developer-local env.d/development/common (which may set e.g.
    RAG_DOCUMENT_PARSER=AdaptivePdfParser) must not leak in, so these resolve to
    Base's deterministic defaults.
    """
    assert settings.RAG_DOCUMENT_PARSER.endswith("AlbertParser")
    assert settings.RAG_DOCUMENT_SEARCH_BACKEND.endswith("AlbertRagBackend")
    assert settings.LLM_DEFAULT_MODEL_HRID == "default-model"


def test_test_only_mechanics_are_pinned(settings):
    """Test-specific backends and mechanics stay in the Test settings class."""
    assert settings.CACHES["default"]["BACKEND"].endswith("LocMemCache")
    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert settings.MALWARE_DETECTION["BACKEND"].endswith("dummy.DummyBackend")


def test_infra_settings_point_at_the_expected_topology(settings):
    """Infra endpoints resolve from the environment (docker default or override).

    Defaults are the docker-compose hostnames; host-run pytest and CI point them
    at the published ports through the repo-root .env or the job env.
    """
    assert settings.DATABASES["default"]["HOST"] == os.environ.get("DB_HOST", "postgresql")
    assert settings.DATABASES["default"]["PORT"] == int(os.environ.get("DB_PORT", "5432"))
    assert settings.AWS_S3_ENDPOINT_URL == os.environ.get(
        "AWS_S3_ENDPOINT_URL", "http://minio:9000"
    )
