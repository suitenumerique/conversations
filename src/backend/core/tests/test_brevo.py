"""Tests for the Brevo API helpers."""

import logging

import httpx
import respx

from core.brevo import add_user_to_brevo_list

ALREADY_IN_LIST_BODY = {
    "code": "invalid_parameter",
    "message": "Contact already in list and/or does not exist",
}


def brevo_logs(caplog):
    """Return the levels of the records emitted by the Brevo helpers."""
    return [record.levelno for record in caplog.records if record.name == "core.brevo"]


@respx.mock
def test_add_user_to_brevo_list_success(settings, caplog):
    """Adding a new contact to a list is not logged."""
    settings.BREVO_API_KEY = "test-api-key"

    respx.post("https://api.brevo.com/v3/contacts").mock(return_value=httpx.Response(201))
    add_to_list = respx.post("https://api.brevo.com/v3/contacts/lists/list-id/contacts/add").mock(
        return_value=httpx.Response(201)
    )

    with caplog.at_level(logging.INFO, logger="core.brevo"):
        add_user_to_brevo_list(["test@example.com"], "list-id")

    assert len(add_to_list.calls) == 1
    assert brevo_logs(caplog) == []


@respx.mock
def test_add_user_to_brevo_list_already_in_list_is_not_an_error(settings, caplog):
    """
    Brevo answers 400 when the contact is already in the list.

    The contact is created right before, so it necessarily exists: this is an expected
    no-op and must not be logged as an error, otherwise every returning user generates
    noise in Sentry.
    """
    settings.BREVO_API_KEY = "test-api-key"

    respx.post("https://api.brevo.com/v3/contacts").mock(return_value=httpx.Response(204))
    respx.post("https://api.brevo.com/v3/contacts/lists/list-id/contacts/add").mock(
        return_value=httpx.Response(400, json=ALREADY_IN_LIST_BODY)
    )

    with caplog.at_level(logging.INFO, logger="core.brevo"):
        add_user_to_brevo_list(["test@example.com"], "list-id")

    assert brevo_logs(caplog) == [logging.INFO]


@respx.mock
def test_add_user_to_brevo_list_genuine_failure_still_logs_an_error(settings, caplog):
    """Any other Brevo failure is still reported as an error."""
    settings.BREVO_API_KEY = "test-api-key"

    respx.post("https://api.brevo.com/v3/contacts").mock(return_value=httpx.Response(204))
    respx.post("https://api.brevo.com/v3/contacts/lists/list-id/contacts/add").mock(
        return_value=httpx.Response(401, json={"code": "unauthorized", "message": "Key not found"})
    )

    with caplog.at_level(logging.INFO, logger="core.brevo"):
        add_user_to_brevo_list(["test@example.com"], "list-id")

    assert brevo_logs(caplog) == [logging.ERROR]


@respx.mock
def test_add_user_to_brevo_list_other_400_still_logs_an_error(settings, caplog):
    """A 400 that is not the 'already in list' one is still an error."""
    settings.BREVO_API_KEY = "test-api-key"

    respx.post("https://api.brevo.com/v3/contacts").mock(return_value=httpx.Response(204))
    respx.post("https://api.brevo.com/v3/contacts/lists/list-id/contacts/add").mock(
        return_value=httpx.Response(
            400, json={"code": "invalid_parameter", "message": "Invalid list id"}
        )
    )

    with caplog.at_level(logging.INFO, logger="core.brevo"):
        add_user_to_brevo_list(["test@example.com"], "list-id")

    assert brevo_logs(caplog) == [logging.ERROR]
