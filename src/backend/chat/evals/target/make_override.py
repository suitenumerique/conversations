"""Generate the compose override that runs a git tag as an isolated eval target.

Reads `docker compose config --format json` of the tag on stdin, writes YAML on
stdout. Stdlib only: it runs on the host, outside the backend image.
"""

import argparse
import json
import sys

BACKEND_SERVICE = "app-dev"
BACKEND_IMAGE_PREFIX = "conversations:backend"
APP_SERVICES = ("app-dev", "celery-dev")
# Docker Hub dropped these images; upstream moved to quay.io in 025e6ad0.
REHOMED_IMAGES = {"minio/minio": "quay.io/minio/minio", "minio/mc": "quay.io/minio/mc"}
CONTAINER_LLM_CONFIG = "/app/conversations/configuration/llm/custom_llm_configuration.json"


def _uses_backend_image(service: dict) -> bool:
    # Match on the image name, not on `build`: the frontend service is built too
    # and must not be retagged with the backend target image.
    return str(service.get("image", "")).startswith(BACKEND_IMAGE_PREFIX)


def _service_block(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    name: str,
    service: dict,
    services: dict,
    *,
    image: str,
    port: int,
    llm_config_path: str,
    model_hrid: str,
) -> list[str]:
    block = []
    if _uses_backend_image(service):
        block.append(f"    image: {image}")
    elif service.get("image") in REHOMED_IMAGES:
        block.append(f"    image: {REHOMED_IMAGES[service['image']]}")
    if name == BACKEND_SERVICE:
        block += ["    ports: !override", f'      - "{port}:8000"']
    elif service.get("ports"):
        block.append("    ports: !reset []")
    if "lasuite" in (service.get("networks") or {}):
        block += ["    networks: !override", "      - default"]
    if name in APP_SERVICES:
        block += [
            "    volumes:",
            f"      - {llm_config_path}:{CONTAINER_LLM_CONFIG}:ro",
            "    environment:",
            f"      LLM_DEFAULT_MODEL_HRID: {model_hrid}",
            # Web search is gated per dataset by the eval user's smart-search
            # opt-in (off by default, as in prod); the data.gouv tool stays off.
            "      FEATURE_FLAG_WEB_SEARCH: ENABLED",
            "      FEATURE_FLAG_DATAGOUV_CONNECTOR: DISABLED",
            # Every case creates a conversation (and project cases a project);
            # lift the per-user creation throttles (20 and 10/hour by default
            # since v0.0.23). Older tags ignore them.
            '      API_CONVERSATION_CREATE_HOURLY_THROTTLE_RATE: "100000/hour"',
            '      API_CONVERSATION_CREATE_DAILY_THROTTLE_RATE: "1000000/day"',
            '      API_PROJECT_CREATE_HOURLY_THROTTLE_RATE: "100000/hour"',
            '      API_PROJECT_CREATE_DAILY_THROTTLE_RATE: "1000000/day"',
        ]
        if "minio" in services and "objectstorage" not in services:
            block.append("      AWS_S3_ENDPOINT_URL: http://minio:9000")
    return block


def build_override(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    config: dict,
    *,
    image: str,
    port: int,
    llm_config_path: str,
    model_hrid: str,
    network_name: str,
) -> str:
    """Return override YAML isolating the target from the current stack."""
    services = config["services"]
    lines = ["services:"]
    for name in sorted(services):
        block = _service_block(
            name,
            services[name],
            services,
            image=image,
            port=port,
            llm_config_path=llm_config_path,
            model_hrid=model_hrid,
        )
        if block:
            lines += [f"  {name}:", *block]
    if "lasuite" in config.get("networks", {}):
        lines += ["networks:", "  lasuite:", f"    name: {network_name}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--llm-config", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--network-name", required=True)
    args = parser.parse_args()
    sys.stdout.write(
        build_override(
            json.load(sys.stdin),
            image=args.image,
            port=args.port,
            llm_config_path=args.llm_config,
            model_hrid=args.model,
            network_name=args.network_name,
        )
    )


if __name__ == "__main__":
    main()
