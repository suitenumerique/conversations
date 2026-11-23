"""What request log lines record of the path."""

from django.core.cache import cache
from django.test import Client

import pytest

pytestmark = pytest.mark.django_db

# A temporary file-stream key: it grants access to the file, so it is never logged.
# Deliberately not random-looking, so secret scanners do not flag it.
TEMPORARY_KEY = "x" * 24
FILE_STREAM_PATH = f"/api/v1.0/file-stream/{TEMPORARY_KEY}/"
REDACTED_PATH = "/api/v1.0/file-stream/[redacted]/"


def _logged_requests(json_logs):
    """The `request` field of each request lifecycle line."""
    return [
        line["request"]
        for line in json_logs()
        if line["event"] in ("request_started", "request_finished")
    ]


def test_a_file_stream_key_is_redacted(json_logs):
    """The method and the rest of the path stay; the key does not."""
    Client().get(FILE_STREAM_PATH)

    assert _logged_requests(json_logs) == [f"GET {REDACTED_PATH}"] * 2
    assert TEMPORARY_KEY not in str(json_logs())


def test_a_live_key_is_redacted_from_django_request_lines(json_logs):
    """A refused request leaves the key live; django.request logs its path."""
    cache.set(f"file_access:{TEMPORARY_KEY}", "attachments/file.pdf")

    response = Client().post(FILE_STREAM_PATH)

    assert response.status_code == 405
    assert cache.get(f"file_access:{TEMPORARY_KEY}") is not None
    django_lines = [line["event"] for line in json_logs() if line["logger"] == "django.request"]
    assert django_lines == [f"Method Not Allowed: {REDACTED_PATH}"]
    assert TEMPORARY_KEY not in str(json_logs())


def test_other_paths_are_logged_unchanged(json_logs):
    """Only the file-stream key is redacted."""
    Client().get("/api/v1.0/config/")

    assert _logged_requests(json_logs) == ["GET /api/v1.0/config/"] * 2
