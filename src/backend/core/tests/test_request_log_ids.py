"""Request log lines carry the ingress request id, not a second one of their own."""

import re

from django.test import AsyncClient, Client

import pytest

pytestmark = pytest.mark.django_db

CONFIG_URL = "/api/v1.0/config/"
INGRESS_REQUEST_ID = "634ab47a476a56b0d7d0503950605134"


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


@pytest.mark.parametrize(
    "header",
    [
        None,  # Dockerflow generates a dashed uuid4
        INGRESS_REQUEST_ID.upper(),
        'id"},{"injected":"1',
    ],
)
def test_a_request_id_not_shaped_like_an_ingress_one_is_replaced(header, json_logs):
    """The request gets a generated 32-hex id, the shape of a Langfuse trace id."""
    Client().get(CONFIG_URL, headers={"X-Request-ID": header} if header else {})

    request_ids = _request_ids(json_logs)
    assert request_ids["request_started"] == request_ids["request_finished"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_ids["request_started"])
    if header:
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
