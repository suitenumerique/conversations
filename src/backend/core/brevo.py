"""Functions for interacting with Brevo API to manage contacts in a waiting list."""

import logging
from typing import List, Optional

from django.conf import settings

import requests

logger = logging.getLogger(__name__)


def add_user_to_brevo_list(emails: List[str], list_id: Optional[str]) -> None:
    """
    Add email list to a Brevo list.

    Args:
        emails (List[str]): The email address(es) of the user(s).
        list_id (str): The Brevo waiting list ID, can be None if not configured.

    """
    api_key = settings.BREVO_API_KEY
    if not api_key or not list_id:
        logger.info("Brevo API key or list ID not configured: skipping adding contact")
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
        response = requests.post(url, json=payload, headers=headers, timeout=5)
    except requests.RequestException as e:
        logger.exception(e)
        return

    if response.status_code != 201:
        logger.error(
            "Error adding contacts to Brevo (%s) %s: (%s) %s",
            list_id,
            emails,
            response.status_code,
            response.text,
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
        logger.info("Brevo API key or list ID not configured: skipping removing contact")
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
        response = requests.post(url, json=payload, headers=headers, timeout=5)
    except requests.RequestException as e:
        logger.exception(e)
        return
    if response.status_code != 201:
        logger.error(
            "Error removing contacts from Brevo (%s) %s: (%s) %s",
            list_id,
            emails,
            response.status_code,
            response.text,
        )
