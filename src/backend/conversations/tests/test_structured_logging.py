"""Tests for the structured (JSON) logs."""

import json
import logging

from django.test import RequestFactory

import pytest

from core.factories import UserFactory

from conversations.observability_settings import ObservabilitySettings
from conversations.settings import Development, Production


def test_production_logs_json_development_keeps_console():
    """Production renders JSON lines for Loki, development stays human-readable."""
    assert Production.LOGGING["handlers"]["console"]["formatter"] == "json"
    assert Development.LOGGING["handlers"]["console"]["formatter"] == "console"


@pytest.mark.parametrize("logger_name", ["request.summary", "uvicorn.access"])
def test_duplicate_request_logs_are_off(logger_name):
    """Requests are logged once, by RequestLogMiddleware, without the query string."""
    logger_config = ObservabilitySettings.LOGGING["loggers"][logger_name]

    assert logger_config["handlers"] == []
    assert logger_config["propagate"] is False


@pytest.mark.django_db
def test_request_logs_have_no_query_string_nor_ip(api_client, json_logs):
    """Request logs carry ids for correlation, never user input or client IPs."""
    user = UserFactory()
    api_client.force_login(user)

    response = api_client.get("/api/v1.0/chats/?title=secret-search")

    assert response.status_code == 200
    request_logs = [
        line for line in json_logs() if line["logger"] == "django_structlog.middlewares.request"
    ]
    assert [line["event"] for line in request_logs] == ["request_started", "request_finished"]
    for line in request_logs:
        assert line["request"] == "GET /api/v1.0/chats/"
        assert line["user_id"] == str(user.pk)
        assert line["request_id"]
        assert "ip" not in line
    assert "secret-search" not in json.dumps(json_logs())


def test_stdlib_record_is_one_json_line_without_extra(json_logs):
    """Tracebacks stay in the line; extra attributes (django.request's request) are dropped."""
    request = RequestFactory().get("/api/v1.0/chats/?title=secret-search")

    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("chat.tests").exception("failed", extra={"request": request})

    [line] = json_logs()
    assert line["event"] == "failed"
    assert line["level"] == "error"
    assert line["logger"] == "chat.tests"
    assert line["timestamp"]
    assert "ValueError: boom" in line["exception"]
    assert "secret-search" not in json.dumps(line)
