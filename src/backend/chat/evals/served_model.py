"""Find the model that actually answers for an LLM configuration.

Providers may serve a requested model name as an alias of another model (Albert answers
`mistral-medium-2508` with `mistral-medium-3-5-0`). Only streamed chunks carry the serving
model's name, so this sends one short streamed request.

Self-contained (Django settings and httpx only): `target/run_target.sh` pipes this file
into `manage.py shell` inside a git ref's containers, whatever their code version,
followed by a `report_served_model(...)` call.
"""

import json
import sys

from django.conf import settings

import httpx


def served_model(hrid: str) -> str | None:
    """Name of the model answering a one-token streamed request for `hrid`."""
    config = settings.LLM_CONFIGURATIONS[hrid]
    base_url = str(config.provider.base_url).rstrip("/")
    # Mistral's base URL is the API root; OpenAI-compatible ones (Albert) already end in /v1.
    if config.provider.kind == "mistral":
        base_url += "/v1"
    with httpx.stream(
        "POST",
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {config.provider.api_key}"},
        json={
            "model": config.model_name,
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1,
            "stream": True,
        },
        timeout=60,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data: {"):
                return json.loads(line.removeprefix("data: ")).get("model")
    return None


def report_served_model(hrid: str, write=sys.stdout.write) -> str | None:
    """Write which model serves `hrid`, warning on aliases; return the served name."""
    requested = settings.LLM_CONFIGURATIONS[hrid].model_name
    served = served_model(hrid)
    write(f"model {hrid}: requested {requested}, served by {served}\n")
    # A suffix is a version of the same model ("mistral-medium-3-5-0"); another name is an alias.
    if not (served or "").startswith(requested):
        write(f"WARNING: the provider serves {requested} as {served}\n")
    return served
