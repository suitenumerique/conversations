"""Functions for interacting with Brevo API to manage contacts in a waiting list."""

from typing import List, Optional

from django.conf import settings

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Brevo answers the "add to list" endpoint with a 400 when it has nothing to add.
# The message is ambiguous on purpose ("already in list" OR "does not exist"), but we
# always create the contact right before adding it, so only the first branch can apply:
# this is an expected no-op, not a failure.
BREVO_NOTHING_TO_ADD_MESSAGE = "Contact already in list and/or does not exist"


def create_contact_in_brevo(email: str) -> bool:
    """
    Create a contact in Brevo.

    Args:
        email (str): The email address of the user.

    """
    api_key = settings.BREVO_API_KEY
    if not api_key:
        logger.info("brevo_contact_creation_skipped_not_configured")
        return False

    url = "https://api.brevo.com/v3/contacts"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    payload = {
        "email": email,
        "updateEnabled": True,
    }
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=5)
    except httpx.HTTPError:
        logger.exception("brevo_contact_creation_request_failed")
        return False

    if not response.is_success:
        logger.error("brevo_contact_creation_failed", status_code=response.status_code)
        return False

    return True


def add_user_to_brevo_list(emails: List[str], list_id: Optional[str]) -> None:
    """
    Add email list to a Brevo list.

    Args:
        emails (List[str]): The email address(es) of the user(s).
        list_id (str): The Brevo waiting list ID, can be None if not configured.

    """
    api_key = settings.BREVO_API_KEY
    if not api_key or not list_id:
        logger.info("brevo_list_add_skipped_not_configured")
        return

    for email in emails:
        # Ensure the contact exists before adding to the list
        # `emails` contains several emails only when used from the admin interface bulk action
        if not create_contact_in_brevo(email):
            logger.error("brevo_list_add_skipped_contact_creation_failed")
            return

    url = f"https://api.brevo.com/v3/contacts/lists/{list_id}/contacts/add"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    payload = {
        "emails": emails,
    }
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=5)
    except httpx.HTTPError:
        logger.exception("brevo_list_add_request_failed", list_id=list_id)
        return

    if response.status_code != 201:
        if response.status_code == 400 and BREVO_NOTHING_TO_ADD_MESSAGE in response.text:
            logger.info("brevo_contacts_already_in_list", list_id=list_id, count=len(emails))
            return

        logger.error(
            "brevo_list_add_failed",
            list_id=list_id,
            count=len(emails),
            status_code=response.status_code,
        )


def remove_user_from_brevo_list(emails: List[str], list_id: Optional[str]) -> None:
    """
    Remove email list from a Brevo list.

    Args:
        emails (List[str]): The email address(es) of the user(s).
        list_id (str): The Brevo waiting list ID, can be None if not configured.

    """
    api_key = settings.BREVO_API_KEY
    if not api_key or not list_id:
        logger.info("brevo_list_remove_skipped_not_configured")
        return

    url = f"https://api.brevo.com/v3/contacts/lists/{list_id}/contacts/remove"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    payload = {
        "emails": emails,
    }
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=5)
    except httpx.HTTPError:
        logger.exception("brevo_list_remove_request_failed", list_id=list_id)
        return
    if response.status_code != 201:
        logger.error(
            "brevo_list_remove_failed",
            list_id=list_id,
            count=len(emails),
            status_code=response.status_code,
        )
