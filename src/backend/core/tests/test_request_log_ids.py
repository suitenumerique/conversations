"""Request log lines carry Dockerflow's request id, not a second one of their own."""

import uuid
from unittest.mock import patch

from django.test import AsyncClient, Client

import pytest

pytestmark = pytest.mark.django_db

CONFIG_URL = "/api/v1.0/config/"
INGRESS_REQUEST_ID = "ingress-request-id-1"
GENERATED_REQUEST_ID = "dockerflow-generated-id-1"


def _request_ids(json_logs):
    """The request_id of each request lifecycle line, by event."""
    return {
        line["event"]: line.get("request_id")
        for line in json_logs()
        if line["event"] in ("request_started", "request_finished")
    }


def test_request_lines_carry_the_ingress_request_id(json_logs):
    """The ingress `X-Request-ID`, as Dockerflow reads it, names every request line."""
    Client().get(CONFIG_URL, headers={"X-Request-ID": INGRESS_REQUEST_ID})

    assert _request_ids(json_logs) == {
        "request_started": INGRESS_REQUEST_ID,
        "request_finished": INGRESS_REQUEST_ID,
    }


def test_request_lines_carry_the_id_dockerflow_generated(json_logs):
    """Without the header, Dockerflow's generated id is used, not a second one."""
    with patch(
        "dockerflow.django.middleware.get_or_generate_request_id",
        return_value=GENERATED_REQUEST_ID,
    ):
        Client().get(CONFIG_URL)

    assert _request_ids(json_logs) == {
        "request_started": GENERATED_REQUEST_ID,
        "request_finished": GENERATED_REQUEST_ID,
    }


@pytest.mark.parametrize(
    "header",
    [
        "a" * 65,  # too long to be an ingress or uuid id
        "id with spaces",
        'id"},{"injected":"1',
    ],
)
def test_an_untrusted_request_id_header_is_not_logged(header, json_logs):
    """A client-chosen id that cannot be an ingress one keeps the generated id."""
    Client().get(CONFIG_URL, headers={"X-Request-ID": header})

    request_ids = _request_ids(json_logs)
    assert request_ids["request_started"] == request_ids["request_finished"]
    # django-structlog's own uuid4, not the header.
    assert uuid.UUID(request_ids["request_started"]).version == 4
    assert header not in str(json_logs())


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_request_lines_carry_the_ingress_request_id_async(json_logs):
    """ASGI: Dockerflow and django-structlog each run in a sync_to_async thread."""
    await AsyncClient().get(CONFIG_URL, headers={"X-Request-ID": INGRESS_REQUEST_ID})

    assert _request_ids(json_logs) == {
        "request_started": INGRESS_REQUEST_ID,
        "request_finished": INGRESS_REQUEST_ID,
    }
