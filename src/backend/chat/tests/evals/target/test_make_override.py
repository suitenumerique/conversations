"""Tests for the compose override that isolates a target stack."""

import pytest

from chat.evals.target.make_override import build_override

LLM_CONFIG = "/repo/src/backend/conversations/configuration/llm/custom_llm_configuration.json"


@pytest.fixture(name="v0021_config")
def v0021_config_fixture():
    """Shape of `docker compose config --format json` for v0.0.21 (relevant keys only)."""
    return {
        "services": {
            "postgresql": {
                "image": "postgres:16",
                "ports": [{"target": 5432, "published": "15432"}],
            },
            "redis": {"image": "redis:5"},
            "minio": {"image": "minio/minio", "ports": [{"target": 9000, "published": "9000"}]},
            "createbuckets": {"image": "minio/mc"},
            "celery-dev": {
                "image": "conversations:backend-development",
                "networks": {"default": None, "lasuite": None},
            },
            "app-dev": {
                "build": {"context": "."},
                "image": "conversations:backend-development",
                "ports": [{"target": 8000, "published": "8071"}],
                "networks": {"default": None, "lasuite": None},
            },
            "frontend-development": {
                "build": {"context": "."},
                "image": "conversations:frontend-development",
                "ports": [{"target": 3000, "published": "3000"}],
            },
            "nginx": {"image": "nginx:1.25", "ports": [{"target": 8083, "published": "8083"}]},
        },
        "networks": {"default": {}, "lasuite": {"name": "lasuite-network"}},
    }


@pytest.fixture(name="override")
def override_fixture(v0021_config):
    """Override generated for v0.0.21 + 2508."""
    return build_override(
        v0021_config,
        image="conversations-target:v0-0-21",
        port=18071,
        llm_config_path=LLM_CONFIG,
        model_hrid="albert-mistral-medium-2508",
        network_name="conv-target-v0-0-21-lasuite",
    )


def test_override_renames_built_images(override):
    """The target never overwrites the current stack's backend image."""
    assert "  app-dev:\n    image: conversations-target:v0-0-21\n" in override


def test_override_leaves_frontend_image_alone(override):
    """Only backend-image services are retagged; the frontend keeps its own image."""
    assert "  frontend-development:\n    ports: !reset []\n" in override
    assert override.count("image: conversations-target:v0-0-21") == 2  # app-dev + celery-dev


def test_override_resets_ports_and_publishes_backend_only(override):
    """Only the backend gets a host port; every other published port is dropped."""
    assert '    ports: !override\n      - "18071:8000"\n' in override
    assert "  postgresql:\n    ports: !reset []\n" in override
    assert "  minio:\n    image: quay.io/minio/minio\n    ports: !reset []\n" in override
    assert "  nginx:\n    ports: !reset []\n" in override
    assert "  redis:" not in override


def test_override_isolates_lasuite_network(override):
    """The named lasuite network is renamed so it never clashes with the current stack."""
    assert "    networks: !override\n      - default\n" in override
    assert "networks:\n  lasuite:\n    name: conv-target-v0-0-21-lasuite\n" in override


def test_override_mounts_llm_config_and_sets_model(override):
    """Backend gets our LLM config, the model under test, web search available, data.gouv off."""
    assert (
        f"      - {LLM_CONFIG}:/app/conversations/configuration/llm/"
        "custom_llm_configuration.json:ro\n" in override
    )
    assert "      LLM_DEFAULT_MODEL_HRID: albert-mistral-medium-2508\n" in override
    assert "      FEATURE_FLAG_WEB_SEARCH: ENABLED\n" in override
    assert "      FEATURE_FLAG_DATAGOUV_CONNECTOR: DISABLED\n" in override


def test_override_points_storage_at_minio_for_old_tags(override):
    """Our env targets 'objectstorage'; tags that only have 'minio' get an infra fallback."""
    assert "      AWS_S3_ENDPOINT_URL: http://minio:9000\n" in override


def test_override_pulls_minio_images_from_quay(override):
    """Docker Hub dropped minio/minio and minio/mc; old tags pull them from quay.io."""
    assert "  minio:\n    image: quay.io/minio/minio\n" in override
    assert "  createbuckets:\n    image: quay.io/minio/mc\n" in override


def test_override_keeps_storage_env_when_objectstorage_exists(v0021_config):
    """Current-code targets already match our env: no storage override."""
    services = v0021_config["services"]
    services["objectstorage"] = services.pop("minio")

    override = build_override(
        v0021_config,
        image="conversations-target:head",
        port=18071,
        llm_config_path=LLM_CONFIG,
        model_hrid="mistral-medium-3-5",
        network_name="conv-target-head-lasuite",
    )

    assert "AWS_S3_ENDPOINT_URL" not in override
    assert "  celery-dev:\n    image: conversations-target:head\n" in override
    assert override.count("LLM_DEFAULT_MODEL_HRID: mistral-medium-3-5") == 2


def test_override_lifts_conversation_creation_throttle(override):
    """Each case creates a conversation; current code throttles that at 20/hour by default."""
    assert '      API_CONVERSATION_CREATE_HOURLY_THROTTLE_RATE: "100000/hour"\n' in override
    assert '      API_CONVERSATION_CREATE_DAILY_THROTTLE_RATE: "1000000/day"\n' in override


def test_override_lifts_project_creation_throttle(override):
    """Project cases create one project per run; current code throttles that at 10/hour."""
    assert '      API_PROJECT_CREATE_HOURLY_THROTTLE_RATE: "100000/hour"\n' in override
    assert '      API_PROJECT_CREATE_DAILY_THROTTLE_RATE: "1000000/day"\n' in override
