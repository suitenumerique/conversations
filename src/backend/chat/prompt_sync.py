"""Synchronization helpers for external prompt repositories."""

from __future__ import annotations

import json
from typing import Iterable

import requests
from django.conf import settings

from chat.models import Prompt


def _raw_url(path: str, commit_sha: str) -> str:
    """
    Build a raw.githubusercontent.com URL for a given file at a specific commit.
    """

    base_url = getattr(settings, "PROMPT_BASE_URL", "https://raw.githubusercontent.com")
    owner = settings.PROMPT_REPO_OWNER
    repo = settings.PROMPT_REPO_NAME

    return f"{base_url}/{owner}/{repo}/{commit_sha}/{path}"


def _fetch_text_file(path: str, commit_sha: str) -> str | None:
    """
    Fetch a text file from the prompts repository at the given commit.
    """

    url = _raw_url(path, commit_sha)
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        return resp.text
    return None


def handle_prompt_sync(payload: dict) -> None:
    """
    Synchronize prompts from the external repository based on a GitHub push payload.

    Strategy V1: full sync for a static list of prompt names.
    This is simple and robust, and prompt files are typically small.
    """

    commit_sha = payload.get("after")
    if not commit_sha:
        # Nothing to do if we don't know which commit to sync from
        return

    # For now, we rely on a static list of prompt names from settings.
    # Example: PROMPT_NAMES = ["assistant_system", "summarizer"]
    prompt_names: Iterable[str] = getattr(
        settings,
        "PROMPT_NAMES",
        ("assistant_system",),
    )

    for name in prompt_names:
        # Try prompts/ subdirectory first, then root as fallback
        jinja_paths = [f"prompts/{name}.jinja", f"{name}.jinja"]
        meta_paths = [f"prompts/{name}.meta.json", f"{name}.meta.json"]

        content = None
        for jinja_path in jinja_paths:
            content = _fetch_text_file(jinja_path, commit_sha)
            if content is not None:
                break

        if content is None:
            # Prompt may have been removed or file missing; we simply skip it for now.
            continue

        metadata = None
        for meta_path in meta_paths:
            metadata_text = _fetch_text_file(meta_path, commit_sha)
            if metadata_text:
                break
        else:
            metadata_text = None
        if metadata_text:
            try:
                metadata = json.loads(metadata_text)
            except json.JSONDecodeError:
                # Ignore invalid metadata for robustness
                metadata = None

        Prompt.objects.update_or_create(
            name=name,
            defaults={
                "version": commit_sha,
                "content": content,
                "metadata": metadata,
            },
        )


